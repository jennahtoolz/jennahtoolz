import OpenAI from 'openai';
import { HttpError, emptyState, object, newSurvey, mutateSurvey, mutateSettings, validateMessages, generateReply } from '../domain.mjs';

const securityHeaders = {
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  'Cache-Control': 'no-store',
};
const json = (data, status = 200) => Response.json(data, { status, headers: securityHeaders });

async function authenticate(request, password) {
  if (typeof password !== 'string' || password.length < 12) {
    throw new HttpError(503, 'Set the QMEE_APP_PASSWORD Worker secret to a password of at least 12 characters before using this deployment.', 'password_not_configured');
  }
  const header = request.headers.get('authorization') || '';
  let decoded = '';
  if (/^Basic /i.test(header)) {
    try { decoded = new TextDecoder().decode(Uint8Array.from(atob(header.slice(6)), c => c.charCodeAt(0))); }
    catch { /* Invalid credentials receive the same challenge. */ }
  }
  const expected = `surveyside:${password}`;
  const hash = async value => new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
  const [a, b] = await Promise.all([hash(decoded), hash(expected)]);
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
  return difference === 0;
}

export class D1Store {
  constructor(db) { this.db = db.withSession('first-primary'); }
  async row() {
    await this.db.prepare('INSERT OR IGNORE INTO dashboard (id, data, revision) VALUES (1, ?, 0)').bind(JSON.stringify(emptyState())).run();
    const row = await this.db.prepare('SELECT data, revision FROM dashboard WHERE id = 1').first();
    if (!row) throw new Error('Dashboard storage unavailable');
    return row;
  }
  async read() { return JSON.parse((await this.row()).data); }
  async update(fn) {
    // Optimistic concurrency keeps each request atomic across Worker instances.
    for (let attempt = 0; attempt < 16; attempt++) {
      const row = await this.row();
      const state = JSON.parse(row.data);
      const value = fn(state);
      const result = await this.db.prepare('UPDATE dashboard SET data = ?, revision = revision + 1 WHERE id = 1 AND revision = ?')
        .bind(JSON.stringify(state), row.revision).run();
      if (result.meta.changes === 1) return { state, value };
    }
    throw new HttpError(409, 'Your log changed while saving. Please try again.');
  }
  async acquireAI() {
    const owner = crypto.randomUUID();
    const now = Date.now();
    const result = await this.db.prepare(`INSERT INTO ai_lease (id, owner, expires_at) VALUES (1, ?, ?)
      ON CONFLICT(id) DO UPDATE SET owner = excluded.owner, expires_at = excluded.expires_at WHERE ai_lease.expires_at <= ?`)
      .bind(owner, now + 60_000, now).run();
    return result.meta.changes === 1 ? owner : null;
  }
  async releaseAI(owner) { await this.db.prepare('DELETE FROM ai_lease WHERE id = 1 AND owner = ?').bind(owner).run(); }
}

async function body(request) {
  const chunks = [];
  let size = 0;
  if (request.body) {
    const reader = request.body.getReader();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 64 * 1024) { await reader.cancel(); throw new HttpError(413, 'This request is too large.'); }
      chunks.push(value);
    }
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return object(JSON.parse(new TextDecoder().decode(bytes))); }
  catch (error) { if (error instanceof HttpError) throw error; throw new HttpError(400, 'Send valid JSON.'); }
}

export async function handleRequest(request, env, { aiClient } = {}) {
  try {
    // Guard both static assets and API routes; no public AI endpoint or survey log.
    if (!await authenticate(request, env.QMEE_APP_PASSWORD)) {
      return new Response('Sign in with username surveyside and your app password.', { status: 401,
        headers: { ...securityHeaders, 'WWW-Authenticate': 'Basic realm="SurveySide", charset="UTF-8"' } });
    }
    const url = new URL(request.url);
    if (request.headers.has('origin') && request.headers.get('origin') !== url.origin) {
      throw new HttpError(403, 'Requests must come from this dashboard.');
    }
    const path = url.pathname;
    const method = request.method;
    const aiConfigured = Boolean(aiClient || env.QMEE_AI_API_KEY);
    if (path === '/api/health' && method === 'GET') return json({ ok: true, aiConfigured });
    if (!path.startsWith('/api/')) {
      if (!['GET', 'HEAD'].includes(method)) throw new HttpError(405, 'Method not allowed.');
      const response = await env.ASSETS.fetch(request);
      const secured = new Response(response.body, response);
      for (const [key, value] of Object.entries(securityHeaders)) secured.headers.set(key, value);
      return secured;
    }
    const store = new D1Store(env.DB);
    if (path === '/api/state' && method === 'GET') return json({ ...await store.read(), aiConfigured });
    if (path === '/api/surveys' && method === 'POST') {
      const survey = newSurvey(await body(request));
      await store.update(state => state.surveys.push(survey));
      return json(survey, 201);
    }
    const match = path.match(/^\/api\/surveys\/([a-f0-9-]+)$/);
    if (match && ['PATCH', 'DELETE'].includes(method)) {
      const input = method === 'PATCH' ? await body(request) : null;
      const result = await store.update(state => mutateSurvey(state, match[1], method, input));
      return json(result.value);
    }
    if (path === '/api/settings' && method === 'PATCH') {
      const input = await body(request);
      const result = await store.update(state => mutateSettings(state, input));
      return json({ ...result.state, aiConfigured });
    }
    if (path === '/api/assistant' && method === 'POST') {
      const { messages } = await body(request);
      validateMessages(messages);
      if (!aiConfigured) throw new HttpError(503, 'Add QMEE_AI_API_KEY in your Cloudflare Worker’s Settings → Variables and Secrets.', 'ai_not_configured');
      const lease = await store.acquireAI();
      if (!lease) throw new HttpError(429, 'One question is already in progress. Please wait for it to finish.');
      try {
        const client = aiClient || new OpenAI({ apiKey: env.QMEE_AI_API_KEY, timeout: 30_000, maxRetries: 0 });
        return json(await generateReply(client, messages, await store.read(), env.QMEE_AI_MODEL || 'gpt-4.1-mini'));
      } finally { await store.releaseAI(lease); }
    }
    throw new HttpError(404, 'Not found.');
  } catch (error) {
    return json({ error: error instanceof HttpError ? error.message : 'Could not load or save the dashboard. Check that the D1 migration has been applied.',
      code: error instanceof HttpError ? error.code : 'server_error' }, error instanceof HttpError ? error.status : 500);
  }
}

export default { fetch: handleRequest };
