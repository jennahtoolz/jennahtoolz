import { createServer } from 'node:http';
import { readFile, mkdir, rename, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import OpenAI from 'openai';
import { currencies, HttpError, emptyState, object, newSurvey, mutateSurvey, mutateSettings, validateMessages, generateReply } from './domain.mjs';

const root = dirname(fileURLToPath(import.meta.url));
class Store {
  constructor(path, state) {
    this.path = path;
    this.state = state;
    this.queue = Promise.resolve();
  }
  static async open(path) {
    let state;
    try {
      state = JSON.parse(await readFile(path, 'utf8'));
      if (state.version !== 1 || !Array.isArray(state.surveys) || !currencies.includes(state.currency)
        || !Number.isInteger(state.dailyGoalCents) || state.dailyGoalCents <= 0) {
        throw new Error('Invalid saved dashboard. Restore a valid data file before starting.');
      }
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      state = emptyState();
    }
    return new Store(path, state);
  }
  update(fn) {
    const work = this.queue.then(async () => {
      const draft = structuredClone(this.state);
      const result = fn(draft);
      await mkdir(dirname(this.path), { recursive: true });
      const temp = `${this.path}.tmp`;
      await writeFile(temp, JSON.stringify(draft, null, 2), { mode: 0o600 });
      await rename(temp, this.path);
      this.state = draft;
      return result;
    });
    this.queue = work.catch(() => {});
    return work;
  }
}

async function body(req) {
  let size = 0;
  const chunks = [];
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 64 * 1024) throw new HttpError(413, 'This request is too large.');
    chunks.push(chunk);
  }
  try { return object(JSON.parse(Buffer.concat(chunks).toString())); }
  catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(400, 'Send valid JSON.');
  }
}
function json(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(data));
}

export async function createApp({
  dataFile = process.env.QMEE_DATA_FILE || join(root, '.data', 'dashboard.json'),
  apiKey = process.env.QMEE_AI_API_KEY,
  model = process.env.QMEE_AI_MODEL || 'gpt-4.1-mini',
  aiClient,
} = {}) {
  const store = await Store.open(dataFile);
  const client = aiClient || (apiKey ? new OpenAI({ apiKey, timeout: 30_000, maxRetries: 0 }) : null);
  let aiBusy = false;
  const staticFiles = {
    '/': ['index.html', 'text/html; charset=utf-8'],
    '/styles.css': ['styles.css', 'text/css; charset=utf-8'],
    '/app.js': ['app.js', 'text/javascript; charset=utf-8'],
    '/metrics.mjs': ['metrics.mjs', 'text/javascript; charset=utf-8'],
  };
  return createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    try {
      const url = new URL(req.url, 'http://localhost');
      const method = req.method;
      if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`
        && req.headers.origin !== `https://${req.headers.host}`) {
        throw new HttpError(403, 'Requests must come from this dashboard.');
      }
      const hostname = (req.headers.host || '').replace(/:\d+$/, '');
      if (!['localhost', '127.0.0.1', '[::1]'].includes(hostname)) throw new HttpError(403, 'Use a local dashboard address.');
      if (method === 'GET' && url.pathname === '/api/health') {
        return json(res, 200, { ok: true, aiConfigured: Boolean(client) });
      }
      if (method === 'GET' && url.pathname === '/api/state') {
        return json(res, 200, { ...store.state, aiConfigured: Boolean(client) });
      }
      if (method === 'POST' && url.pathname === '/api/surveys') {
        const input = await body(req);
        const survey = newSurvey(input);
        await store.update(state => state.surveys.push(survey));
        return json(res, 201, survey);
      }
      const match = url.pathname.match(/^\/api\/surveys\/([a-f0-9-]+)$/);
      if (match && ['PATCH', 'DELETE'].includes(method)) {
        const input = method === 'PATCH' ? await body(req) : null;
        const result = await store.update(state => mutateSurvey(state, match[1], method, input));
        return json(res, 200, result);
      }
      if (method === 'PATCH' && url.pathname === '/api/settings') {
        const input = await body(req);
        await store.update(state => mutateSettings(state, input));
        return json(res, 200, { ...store.state, aiConfigured: Boolean(client) });
      }
      if (method === 'POST' && url.pathname === '/api/assistant') {
        const input = await body(req);
        validateMessages(input.messages);
        if (!client) throw new HttpError(503, 'Connect AI by adding QMEE_AI_API_KEY in environment settings, then restart the app.', 'ai_not_configured');
        if (aiBusy) throw new HttpError(429, 'One question is already in progress. Please wait for it to finish.');
        aiBusy = true;
        try {
          return json(res, 200, await generateReply(client, input.messages, store.state, model));
        } finally { aiBusy = false; }
      }
      if (method === 'GET' && staticFiles[url.pathname]) {
        const [file, type] = staticFiles[url.pathname];
        const data = await readFile(join(root, 'public', file));
        res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-cache' });
        return res.end(data);
      }
      throw new HttpError(404, 'Not found.');
    } catch (error) {
      if (res.headersSent) return res.end();
      json(res, error.status || 500, { error: error.status ? error.message : 'Could not save or load dashboard data. Try again.', code: error.code || 'server_error' });
    }
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be between 1 and 65535.');
  const app = await createApp();
  app.listen(port, '127.0.0.1', () => console.log(`SurveySide listening on port ${port}. AI ${process.env.QMEE_AI_API_KEY ? 'configured' : 'not configured'}.`));
  app.on('error', error => { console.error(`Startup failed: ${error.code || error.message}`); process.exitCode = 1; });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { app.close(); app.closeIdleConnections(); });
}
