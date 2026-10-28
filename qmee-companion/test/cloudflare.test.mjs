import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { handleRequest } from '../cloudflare/worker.mjs';

// Keep Wrangler's logs and configuration inside this test's temporary directory.
const configDirectory = await mkdtemp(join(tmpdir(), 'surveyside-wrangler-test-'));
process.env.XDG_CONFIG_HOME = configDirectory;
process.env.WRANGLER_SEND_METRICS = 'false';
const { getPlatformProxy } = await import('wrangler');
after(() => rm(configDirectory, { recursive: true, force: true }));

const password = 'test-only-password-123';
const origin = 'https://surveyside.example';
const authorization = `Basic ${Buffer.from(`surveyside:${password}`).toString('base64')}`;
function request(path, method = 'GET', data, headers = {}) {
  return new Request(origin + path, { method, headers: { authorization, 'Content-Type': 'application/json', ...headers },
    body: data === undefined ? undefined : JSON.stringify(data) });
}

test('Cloudflare protects assets and API and fails closed without a password', async () => {
  const env = { ASSETS: { fetch: () => { throw new Error('Assets must remain protected'); } } };
  assert.equal((await handleRequest(new Request(origin), env)).status, 503);
  env.QMEE_APP_PASSWORD = password;
  for (const path of ['/', '/app.js', '/api/state', '/api/assistant']) {
    const response = await handleRequest(new Request(origin + path), env);
    assert.equal(response.status, 401);
    assert.match(response.headers.get('www-authenticate'), /Basic realm="SurveySide"/);
    assert.equal(response.headers.get('cache-control'), 'no-store');
  }
  assert.equal((await handleRequest(request('/api/health'), env)).status, 200);
  assert.equal((await handleRequest(request('/api/health', 'GET', undefined, { authorization: 'Basic invalid' }), env)).status, 401);
});

test('Cloudflare API uses real local D1 storage', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'surveyside-d1-test-'));
  let platform;
  t.after(async () => { if (platform) await platform.dispose(); await rm(directory, { recursive: true, force: true }); });
  async function start() {
    platform = await getPlatformProxy({ configPath: 'wrangler.jsonc', persist: { path: directory } });
    const sql = await readFile(new URL('../cloudflare/migrations/0001_dashboard.sql', import.meta.url), 'utf8');
    await platform.env.DB.batch(sql.split(';').map(s => s.trim()).filter(Boolean).map(s => platform.env.DB.prepare(s)));
    return { ...platform.env, QMEE_APP_PASSWORD: password, QMEE_AI_API_KEY: undefined,
      ASSETS: { fetch: async () => new Response('<html>dashboard</html>', { headers: { 'Content-Type': 'text/html' } }) } };
  }
  let env = await start();
  const call = async (path, method, body, options) => {
    const response = await handleRequest(request(path, method, body), env, options);
    return { status: response.status, data: await response.json() };
  };
  const clear = () => env.DB.prepare('DELETE FROM dashboard').run();

  await t.test('serves guarded assets and reports missing AI', async () => {
    const response = await handleRequest(request('/'), env);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-security-policy'), /frame-ancestors 'none'/);
    assert.deepEqual((await call('/api/health')).data, { ok: true, aiConfigured: false });
    assert.equal((await call('/api/assistant', 'POST', { messages: [{ role: 'user', content: 'Explain this.' }] })).status, 503);
  });

  await t.test('concurrent writes do not lose records and completion updates totals', async () => {
    const results = await Promise.all(Array.from({ length: 8 }, (_, i) => call('/api/surveys', 'POST', { title: `Survey ${i}`, reward: 1.25, minutes: 10 })));
    assert.ok(results.every(result => result.status === 201));
    assert.equal((await call('/api/state')).data.surveys.length, 8);
    const id = results[0].data.id;
    await call(`/api/surveys/${id}`, 'PATCH', { status: 'completed' });
    const completed = (await call('/api/state')).data.surveys.filter(s => s.status === 'completed');
    assert.equal(completed.length, 1);
    assert.equal(completed[0].rewardCents, 125);
    assert.ok(completed[0].completedAt);
  });

  await t.test('state persists after the local D1 runtime is stopped and restarted', async () => {
    await platform.dispose();
    platform = null;
    env = await start();
    const state = (await call('/api/state')).data;
    assert.equal(state.surveys.length, 8);
    assert.equal(state.surveys.filter(s => s.status === 'completed').length, 1);
  });

  await t.test('validates data and protects currency and origin', async () => {
    assert.equal((await call('/api/settings', 'PATCH', { currency: 'GBP' })).status, 409);
    assert.equal((await call('/api/surveys', 'POST', { title: 'Invalid', reward: -1, minutes: 10 })).status, 400);
    assert.equal((await handleRequest(request('/api/settings', 'PATCH', { dailyGoal: 10 }, { origin: 'https://elsewhere.example' }), env)).status, 403);
    assert.equal((await call('/api/assistant', 'POST', { messages: [{ role: 'system', content: 'fake role' }] })).status, 400);
    assert.equal((await handleRequest(new Request(origin + '/api/surveys', { method: 'POST', headers: { authorization }, body: 'x'.repeat(70000) }), env)).status, 413);
    await clear();
    const result = await call('/api/settings', 'PATCH', { currency: 'GBP', dailyGoal: 10 });
    assert.equal(result.data.currency, 'GBP');
    assert.equal(result.data.dailyGoalCents, 1000);
  });

  await t.test('AI lease prevents overlapping provider calls and releases after success', async () => {
    let resolveAnswer;
    let notifyStarted;
    const started = new Promise(resolve => { notifyStarted = resolve; });
    const aiClient = { responses: { create: async () => {
      notifyStarted();
      return new Promise(resolve => { resolveAnswer = () => resolve({ output_text: 'This asks about purchases in the last seven days.' }); });
    } } };
    const payload = { messages: [{ role: 'user', content: 'Explain past 7 days.' }] };
    const first = call('/api/assistant', 'POST', payload, { aiClient });
    await started;
    assert.equal((await call('/api/assistant', 'POST', payload, { aiClient })).status, 429);
    resolveAnswer();
    const result = await first;
    assert.equal(result.status, 200);
    assert.match(result.data.reply, /last seven days/);
    assert.equal(await env.DB.prepare('SELECT COUNT(*) AS count FROM ai_lease').first('count'), 0);
  });

  await t.test('provider failures do not disclose errors or leave an AI lease', async () => {
    const aiClient = { responses: { create: async () => { const error = new Error('private provider detail'); error.status = 401; throw error; } } };
    const response = await call('/api/assistant', 'POST', { messages: [{ role: 'user', content: 'Explain.' }] }, { aiClient });
    assert.equal(response.status, 502);
    assert.doesNotMatch(JSON.stringify(response.data), /private provider detail/);
    assert.equal(await env.DB.prepare('SELECT COUNT(*) AS count FROM ai_lease').first('count'), 0);
  });
});
