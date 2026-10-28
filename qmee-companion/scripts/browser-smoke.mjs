import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { once } from 'node:events';
import { chromium } from 'playwright';
import { createApp } from '../server.mjs';

const folder = await mkdtemp(join(tmpdir(), 'surveyside-browser-'));
const servers = [];
let browser;
async function serve(options = {}) {
  const server = await createApp({ dataFile: join(folder, `${servers.length}.json`), apiKey: null, ...options });
  servers.push(server);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return `http://127.0.0.1:${server.address().port}`;
}
async function waitForText(page, id, text) {
  await page.waitForFunction(({ id, text }) => document.getElementById(id).textContent.includes(text), { id, text });
}
async function screenshot(page, filename) {
  if (!process.env.QMEE_SCREENSHOT_DIR) return;
  await mkdir(process.env.QMEE_SCREENSHOT_DIR, { recursive: true });
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo({ top: 0, behavior: 'instant' }); });
  await page.screenshot({ path: join(process.env.QMEE_SCREENSHOT_DIR, filename), fullPage: true });
}

try {
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true });
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  const origin = await serve();
  await page.goto(origin);
  await waitForText(page, 'today-earned', '$0.00');
  assert.equal(await page.getByRole('button', { name: 'Explain my choices' }).isDisabled(), true);
  assert.equal(await page.locator('#ai-setup').isVisible(), true);

  await page.getByRole('button', { name: 'Add a survey', exact: false }).first().click();
  await page.getByLabel('Survey name', { exact: true }).fill('Shopping <img src=x onerror=alert(1)>');
  await page.getByLabel('Reward (USD)').fill('1.50');
  await page.getByLabel('Estimated minutes').fill('10');
  await waitForText(page, 'rate-preview', '$9.00');
  await page.getByRole('button', { name: 'Add to shortlist' }).click();
  await page.waitForSelector('.survey-name');
  assert.match(await page.locator('.survey-name').textContent(), /<img src=x/);
  assert.equal(await page.locator('.survey-name img').count(), 0);
  await page.locator('.survey-actions summary').click();
  await page.getByRole('button', { name: 'Mark completed' }).click();
  await waitForText(page, 'today-earned', '$1.50');
  await page.locator('#survey-filter').selectOption('completed');
  await page.waitForSelector('.survey-name');
  await page.reload();
  await waitForText(page, 'total-earned', '$1.50');
  await page.locator('#survey-filter').selectOption('completed');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export CSV' }).click();
  const download = await downloadPromise;
  const csv = await readFile(await download.path(), 'utf8');
  assert.match(csv, /Shopping <img/);
  assert.match(csv, /"1.50","USD"/);
  await page.locator('.survey-actions summary').click();
  await page.getByRole('button', { name: 'Remove record', exact: true }).click();
  await page.locator('#delete-dialog').getByRole('button', { name: 'Remove record', exact: true }).click();
  await waitForText(page, 'total-earned', '$0.00');
  await page.getByRole('button', { name: 'Edit daily goal' }).click();
  await page.getByLabel('Currency', { exact: true }).selectOption('GBP');
  await page.locator('#settings-dialog').getByLabel('Daily earnings goal').fill('10');
  await page.getByRole('button', { name: 'Save preferences' }).click();
  await waitForText(page, 'goal-amount', '£10.00');
  await screenshot(page, 'desktop.png');
  console.log('PASS desktop: survey actions, persistence, totals, export, preferences, safe text rendering, missing-key UI');

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  mobile.on('pageerror', error => errors.push(error.message));
  await mobile.goto(origin);
  await waitForText(mobile, 'goal-amount', '£10.00');
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await mobile.getByRole('button', { name: 'Add a survey', exact: false }).first().click();
  assert.equal(await mobile.getByRole('dialog').isVisible(), true);
  await mobile.getByRole('button', { name: 'Cancel', exact: true }).click();
  await screenshot(mobile, 'mobile.png');
  console.log('PASS mobile: 390px layout, no horizontal overflow, working dialog');

  const captured = [];
  const aiClient = { responses: { create: async input => {
    captured.push(input);
    if (captured.length === 3) { const error = new Error('Test usage limit'); error.status = 429; throw error; }
    return { output_text: 'This question asks about the last 30 days. Match the option to purchases during that time.' };
  } } };
  const aiOrigin = await serve({ aiClient });
  const aiPage = await browser.newPage();
  aiPage.on('pageerror', error => errors.push(error.message));
  await aiPage.goto(aiOrigin);
  await waitForText(aiPage, 'ai-status', 'Connected');
  await aiPage.getByLabel('Survey question and answer choices').fill('In the past month, did you buy coffee? Yes / No');
  await aiPage.getByLabel('What’s confusing you?', { exact: false }).fill('Does that mean 30 days?');
  await aiPage.getByRole('button', { name: 'Explain my choices' }).click();
  await aiPage.waitForSelector('.chat-message.assistant');
  assert.match(captured[0].input[0].content, /did you buy coffee/);
  assert.match(captured[0].input[0].content, /Does that mean 30 days/);
  await aiPage.getByLabel('Message your AI assistant').fill('What if I bought it yesterday?');
  await aiPage.getByRole('button', { name: 'Send message', exact: true }).click();
  await aiPage.waitForFunction(() => document.querySelectorAll('.chat-message.assistant').length === 2);
  assert.equal(captured[1].input.length, 3);
  await aiPage.getByLabel('Message your AI assistant').fill('One more question.');
  await aiPage.getByRole('button', { name: 'Send message', exact: true }).click();
  await aiPage.waitForFunction(() => !document.getElementById('chat-error').hidden);
  assert.match(await aiPage.locator('#chat-error').textContent(), /usage or billing limit/);
  assert.equal(await aiPage.locator('#chat-input').inputValue(), 'One more question.');
  assert.equal(await aiPage.locator('#chat-send').isEnabled(), true);
  assert.deepEqual(errors, []);
  console.log('PASS AI UI with simulated provider: question/context delivery, follow-up history, recoverable provider errors');
  console.log('Browser smoke checks complete. No Qmee or live AI requests were made.');
} finally {
  if (browser) await browser.close();
  for (const server of servers) {
    const done = new Promise(resolve => server.close(resolve));
    server.closeAllConnections();
    await done;
  }
  await rm(folder, { recursive: true, force: true });
}
