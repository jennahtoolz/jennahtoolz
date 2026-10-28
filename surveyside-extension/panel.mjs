import {explain} from './ai.mjs';
const $ = id => document.getElementById(id);
let apiKey = '';
let screenshot = '';
let missingOrigins = [];
let busy = false;

function status(text) { $('status').textContent = text; }
function failure(error) { $('error').textContent = error.message || 'Something went wrong. Try again.'; $('error').hidden = false; }
function clearError() { $('error').hidden = true; $('error').textContent = ''; }
function setBusy(value) {
  busy = value;
  for (const node of document.querySelectorAll('button, input, textarea')) node.disabled = value;
}
async function message(input) {
  const response = await chrome.runtime.sendMessage(input);
  if (!response?.ok) throw new Error(response?.error || 'The extension restarted. Reopen it and try again.');
  return response.data;
}
function removeImage() { screenshot = ''; $('capture-image').removeAttribute('src'); $('image-preview').hidden = true; }
function clearAnswer() { $('answer').textContent = ''; $('answer-section').hidden = true; }
async function scan() {
  if (busy) return;
  setBusy(true); clearError(); clearAnswer(); removeImage(); status('Reading the current page…');
  try {
    const capture = await message({type: 'scan'});
    $('question').value = capture.text;
    missingOrigins = capture.missingOrigins;
    $('frame-access').hidden = !missingOrigins.length;
    $('frame-sites').textContent = missingOrigins.map(origin => new URL(origin).hostname).join(', ');
    $('capture-meta').textContent = `${capture.title} · ${capture.frameCount} readable frame${capture.frameCount === 1 ? '' : 's'}${capture.truncated ? ' · text shortened' : ''}`;
    if ($('include-image').checked) {
      screenshot = await message({type: 'capture', tabId: capture.tabId, windowId: capture.windowId});
      $('capture-image').src = screenshot; $('image-preview').hidden = false;
    }
    status(capture.text || screenshot ? 'Captured locally. Review the preview, then ask for help.' : 'No readable text found. Try a screenshot or paste the question.');
  } catch (error) { status(''); failure(error); }
  finally { setBusy(false); }
}
$('scan').addEventListener('click', scan);
$('allow-frames').addEventListener('click', async () => {
  clearError();
  try {
    // Request inside the user gesture, before any asynchronous work.
    const granted = await chrome.permissions.request({origins: missingOrigins});
    if (granted) await scan(); else status('Access was not granted. You can use a screenshot or paste the question.');
  } catch { failure(new Error('Chrome could not grant embedded-site access. Try a screenshot or paste the question.')); }
});
$('remove-image').addEventListener('click', removeImage);
$('clear').addEventListener('click', () => {
  $('question').value = ''; $('note').value = ''; $('capture-meta').textContent = 'Nothing captured yet.';
  missingOrigins = []; $('frame-access').hidden = true; removeImage(); clearAnswer(); clearError(); status('Capture cleared.');
});
$('save').addEventListener('click', async () => {
  clearError();
  try {
    const nextKey = $('api-key').value.trim();
    const model = $('model').value.trim() || 'gemini-flash-latest';
    if (!/^[A-Za-z0-9._-]{1,100}$/.test(model)) throw new Error('Enter a valid Gemini model name.');
    await chrome.storage.session.set({apiKey: nextKey});
    await chrome.storage.local.set({model, facts: $('facts').value});
    apiKey = nextKey; $('key-state').textContent = apiKey ? 'Key saved for session' : 'Add Gemini key';
    $('setup').open = !apiKey; status('Setup saved on this device.');
  } catch (error) { failure(error); }
});
$('forget').addEventListener('click', async () => {
  try { await chrome.storage.session.remove('apiKey'); apiKey = ''; $('api-key').value = ''; $('key-state').textContent = 'Add Gemini key'; status('API key forgotten.'); }
  catch { failure(new Error('Could not clear the key. Close Chrome to clear the session.')); }
});
$('explain').addEventListener('click', async () => {
  if (busy) return;
  clearError(); clearAnswer(); setBusy(true); status('Asking Gemini…');
  try {
    const result = await explain({key: apiKey, model: $('model').value.trim() || 'gemini-flash-latest', question: $('question').value, facts: $('facts').value, note: $('note').value, screenshot});
    $('answer').textContent = result; $('answer-section').hidden = false; status('Explanation ready. Review it alongside your question.');
  } catch (error) { status(''); failure(error); if (!apiKey) $('setup').open = true; }
  finally { setBusy(false); }
});
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('answer').textContent); status('Explanation copied.'); }
  catch { status('Select the explanation text and copy it with your keyboard.'); }
});
try {
  const [local, session] = await Promise.all([chrome.storage.local.get(['model', 'facts']), chrome.storage.session.get('apiKey')]);
  apiKey = session.apiKey || ''; $('api-key').value = apiKey; $('facts').value = local.facts || ''; $('model').value = local.model || 'gemini-flash-latest';
  $('key-state').textContent = apiKey ? 'Key saved for session' : 'Add Gemini key'; $('setup').open = !apiKey;
} catch { failure(new Error('Could not restore setup. Reopen the extension and try again.')); }
