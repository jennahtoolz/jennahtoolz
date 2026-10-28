// Actual DOM/UI in Chromium; Chrome APIs are simulated. This cloud image's
// administrator policy prevents loading unpacked extensions.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {once} from 'node:events';
import {resolve, extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {scanDocument} from '../scanner.mjs';
import {summarizeFrames} from '../scan-results.mjs';
const require = createRequire(new URL('../../qmee-companion/package.json', import.meta.url));
const {chromium} = require('playwright');
const extension = resolve(fileURLToPath(new URL('..', import.meta.url)));
const requests = [], unexpected = [], errors = [];
const storage = {local: {}, session: {}};
const allowedOrigins = new Set(['https://app.qmee.com/*']);
let failProvider = false;
let browser;
const frame = '<!doctype html><html><body><h2>In the past 7 days, did you buy coffee?</h2><label><input type="radio" name="coffee">Yes</label><label><input type="radio" name="coffee">No</label><button>Continue</button></body></html>';
const fixture = `<!doctype html><html><head><title>Local survey fixture</title></head><body><h1>Your survey</h1><p>Choose the answer matching your own purchases.</p><label>Password <input type="password" value="never-scan-this-password"></label><input type="hidden" value="never-scan-hidden-value"><div hidden>never-scan-hidden-text</div><div style="opacity:0">never-scan-transparent-text</div><textarea>never-scan-typed-response</textarea><div id="shadow"></div><iframe title="Local same-origin question" src="/fixture-frame"></iframe><iframe title="Local separate-site question" src="https://survey.fixture.invalid/frame"></iframe><script>document.querySelector('#shadow').attachShadow({mode:'open'}).innerHTML='<p>Open shadow question</p>';window.clickCount=0;document.querySelectorAll('input,button').forEach(node=>node.addEventListener('click',()=>window.clickCount++));</script></body></html>`;
const server = createServer(async (request, response) => {
  const path = resolve(extension, '.' + new URL(request.url, 'http://fixture').pathname);
  if (!path.startsWith(extension + '/')) { response.writeHead(403).end(); return; }
  try {
    const types = {'.html': 'text/html', '.css': 'text/css', '.mjs': 'text/javascript'};
    response.writeHead(200, {'content-type': types[extname(path)] || 'text/plain'}).end(await readFile(path));
  } catch { response.writeHead(404).end(); }
});
server.listen(0, '127.0.0.1'); await once(server, 'listening');
const origin = `http://127.0.0.1:${server.address().port}`;

try {
  browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true});
  const context = await browser.newContext();
  await context.route('**/*', async route => {
    const url = route.request().url();
    if (url.startsWith(origin)) return route.continue();
    if (url.startsWith('https://app.qmee.com/')) return route.fulfill({contentType: 'text/html', body: url.endsWith('/fixture-frame') ? frame : fixture});
    if (url.startsWith('https://survey.fixture.invalid/')) return route.fulfill({contentType: 'text/html', body: '<h2>Cross-site fixture question</h2>'});
    if (url.startsWith('https://generativelanguage.googleapis.com/')) {
      const headers = {'access-control-allow-origin': '*', 'access-control-allow-headers': 'content-type,x-goog-api-key'};
      if (route.request().method() === 'OPTIONS') return route.fulfill({status: 204, headers});
      requests.push({url, headers: route.request().headers(), body: route.request().postDataJSON()});
      return route.fulfill({status: failProvider ? 429 : 200, headers, contentType: 'application/json', body: JSON.stringify(failProvider ? {error: {message: 'fixture-only'}} : {candidates: [{content: {parts: [{text: 'Yes matches buying coffee yesterday. <img src=x onerror=alert(1)>'}]}}]})});
    }
    unexpected.push(url); return route.abort();
  });
  const survey = await context.newPage();
  await survey.goto('https://app.qmee.com/surveyside-local-test');
  await survey.frameLocator('iframe[title="Local same-origin question"]').getByText('In the past 7 days', {exact: false}).waitFor();
  await survey.frameLocator('iframe[title="Local separate-site question"]').getByText('Cross-site fixture question').waitFor();
  await survey.evaluate(() => { const select = document.createElement('select'); select.innerHTML = '<option>Every day</option><option>Once a week</option>'; document.body.append(select); });
  const panel = await context.newPage();
  panel.on('pageerror', error => errors.push(error.message));
  await panel.exposeFunction('__extensionStorage', ({area, method, value}) => {
    if (method === 'get') return Object.fromEntries((value === null ? Object.keys(storage[area]) : Array.isArray(value) ? value : [value]).filter(key => Object.hasOwn(storage[area], key)).map(key => [key, storage[area][key]]));
    if (method === 'set') Object.assign(storage[area], value);
    if (method === 'remove') delete storage[area][value];
  });
  await panel.exposeFunction('__extensionPermission', origins => { for (const item of origins) allowedOrigins.add(item); return true; });
  await panel.exposeFunction('__extensionMessage', async message => {
    if (message.type === 'capture') return {ok: true, data: 'data:image/png;base64,' + (await survey.screenshot()).toString('base64')};
    const results = [];
    for (const [index, frame] of survey.frames().entries()) {
      if (!allowedOrigins.has(new URL(frame.url()).origin + '/*')) continue;
      results.push({frameId: index, result: await frame.evaluate(scanDocument)});
    }
    return {ok: true, data: {tabId: 1, windowId: 1, ...await summarizeFrames(results, async host => allowedOrigins.has(host))}};
  });
  await panel.addInitScript(() => {
    const area = name => ({get: value => window.__extensionStorage({area: name, method: 'get', value}), set: value => window.__extensionStorage({area: name, method: 'set', value}), remove: value => window.__extensionStorage({area: name, method: 'remove', value})});
    Object.assign(window.chrome, {storage: {local: area('local'), session: area('session')}, runtime: {sendMessage: message => window.__extensionMessage(message)}, permissions: {request: ({origins}) => window.__extensionPermission(origins)}});
  });
  await panel.goto(origin + '/panel.html');
  await panel.getByLabel('Gemini API key', {exact: true}).fill('fixture-key-not-real');
  await panel.getByLabel('Your facts', {exact: false}).fill('Bought coffee yesterday.');
  await panel.getByRole('button', {name: 'Save setup', exact: true}).click();
  await panel.waitForFunction(() => document.querySelector('#status').textContent.includes('Setup saved'));
  assert.equal(storage.local.apiKey, undefined);
  assert.equal(storage.session.apiKey, 'fixture-key-not-real');
  await panel.getByRole('button', {name: 'Scan current page', exact: true}).click();
  await panel.waitForFunction(() => document.querySelector('#status').textContent.includes('Captured locally') || !document.querySelector('#error').hidden);
  assert.equal(await panel.locator('#error').isHidden(), true, await panel.locator('#error').textContent());
  let text = await panel.locator('#question').inputValue();
  assert.match(text, /In the past 7 days/);
  assert.match(text, /Yes\nNo/);
  assert.match(text, /Open shadow question/);
  assert.match(text, /Dropdown choices: Every day \/ Once a week/);
  assert.doesNotMatch(text, /never-scan/);
  assert.doesNotMatch(text, /Cross-site fixture question/);
  assert.equal(await panel.locator('#frame-access').isVisible(), true);
  assert.match(await panel.locator('#frame-sites').textContent(), /survey.fixture.invalid/);
  assert.equal(requests.length, 0, 'Scanning must not send data to AI');
  assert.equal(await survey.evaluate(() => window.clickCount), 0, 'Scanning must not press survey choices');
  console.log('PASS browser harness: actual page/iframe/open-shadow DOM scanning, hidden and input exclusions, cross-site access detection, no automatic AI or survey clicks.');
  await panel.getByRole('button', {name: 'Allow embedded survey sites', exact: true}).click();
  await panel.waitForFunction(() => document.querySelector('#question').value.includes('Cross-site fixture question'));
  assert.equal(await panel.locator('#frame-access').isHidden(), true);
  await panel.getByLabel('Include a screenshot', {exact: false}).check();
  await panel.getByRole('button', {name: 'Scan current page', exact: true}).click();
  await panel.locator('#image-preview').waitFor({state: 'visible'});
  assert.match(await panel.locator('#capture-image').getAttribute('src'), /^data:image\/png;base64,/);
  await panel.getByRole('button', {name: 'Explain my choices', exact: true}).click();
  await panel.locator('#answer-section').waitFor({state: 'visible'});
  assert.equal(requests.length, 1);
  assert.match(requests[0].body.contents[0].parts[0].text, /Bought coffee yesterday/);
  assert.equal(requests[0].body.contents[0].parts[1].inlineData.mimeType, 'image/png');
  assert.equal(await panel.locator('#answer img').count(), 0);
  assert.match(await panel.locator('#answer').textContent(), /<img src=x/);
  assert.equal(await survey.evaluate(() => window.clickCount), 0);
  console.log('PASS browser harness: granted-frame rescan, screenshot preview/AI image delivery, simulated explanation rendered as safe text.');
  await panel.getByRole('button', {name: 'Remove screenshot', exact: true}).click();
  assert.equal(await panel.locator('#image-preview').isHidden(), true);
  text = await panel.locator('#question').inputValue();
  failProvider = true;
  await panel.getByRole('button', {name: 'Explain my choices', exact: true}).click();
  await panel.locator('#error').waitFor({state: 'visible'});
  assert.match(await panel.locator('#error').textContent(), /usage or rate limit/);
  assert.equal(await panel.locator('#question').inputValue(), text);
  assert.equal(requests[1].body.contents[0].parts.length, 1);
  assert.equal(await panel.getByRole('button', {name: 'Explain my choices', exact: true}).isEnabled(), true);
  await panel.reload();
  await panel.waitForFunction(() => document.querySelector('#api-key').value === 'fixture-key-not-real');
  assert.equal(await panel.locator('#question').inputValue(), '');
  assert.equal(await panel.locator('#facts').inputValue(), 'Bought coffee yesterday.');
  await panel.locator('#setup').evaluate(element => { element.open = true; });
  await panel.getByRole('button', {name: 'Forget key', exact: true}).click();
  await panel.waitForFunction(() => document.querySelector('#status').textContent.includes('forgotten'));
  await panel.locator('#question').fill('Fixture question');
  await panel.getByRole('button', {name: 'Explain my choices', exact: true}).click();
  await panel.locator('#error').waitFor({state: 'visible'});
  assert.match(await panel.locator('#error').textContent(), /API key/);
  assert.equal(requests.length, 2, 'Missing key must not call the provider');
  await panel.setViewportSize({width: 320, height: 900});
  assert.equal(await panel.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  assert.deepEqual(errors, []);
  assert.deepEqual(unexpected, []);
  console.log('PASS browser harness: quota recovery preserves capture; key storage/removal; capture clears on reload; 320px layout fits.');
  console.log('Chrome APIs and Gemini responses were simulated. Cloud administrator policy blocks unpacked extension installation; actual Chrome installation and live Qmee/Gemini remain unverified.');
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
