import {scanDocument} from './scanner.mjs';
import {summarizeFrames} from './scan-results.mjs';
import {drawCircle, clearCircle} from './circle.mjs';

chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {});

async function activeTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab?.id) throw new Error('Open a survey tab first.');
  if (tab.url && !/^https?:\/\//.test(tab.url)) throw new Error('Open a regular website. Chrome settings and Web Store pages cannot be scanned.');
  return tab;
}

export async function scan() {
  const tab = await activeTab();
  let results;
  try {
    results = await chrome.scripting.executeScript({target: {tabId: tab.id, allFrames: true}, func: scanDocument});
  } catch {
    // A restricted child frame must not prevent reading a permitted main page.
    try { results = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: scanDocument}); }
    catch { throw new Error('Click the SurveySide toolbar icon on this website, then scan again. Chrome may need to grant access to this tab.'); }
  }
  return {tabId: tab.id, windowId: tab.windowId, ...await summarizeFrames(results, origin => chrome.permissions.contains({origins: [origin]}))};
}

export async function captureTab(tabId, windowId) {
  const current = await activeTab();
  if (current.id !== tabId || current.windowId !== windowId) throw new Error('The active tab changed. Scan the current question again.');
  let dataUrl;
  try { dataUrl = await chrome.tabs.captureVisibleTab(windowId, {format: 'png'}); }
  catch { throw new Error('Chrome needs a click on the SurveySide toolbar icon to allow a screenshot. Click it, then scan again.'); }
  const after = await activeTab();
  if (after.id !== tabId || after.windowId !== windowId) throw new Error('The active tab changed during capture. Scan again.');
  return dataUrl;
}

export async function circleOption({tabId, windowId, choice}) {
  const current = await activeTab();
  if (current.id !== tabId || current.windowId !== windowId) throw new Error('The active tab changed. Scan the current survey again.');
  if (!choice || !Number.isInteger(choice.frameId) || typeof choice.localId !== 'string' || typeof choice.scanId !== 'string') throw new Error('No captured option matches this suggestion. Scan again.');
  const target = choice.documentId ? {tabId, documentIds: [choice.documentId]} : {tabId, frameIds: [choice.frameId]};
  let results;
  try { results = await chrome.scripting.executeScript({target, func: drawCircle, args: [{scanId: choice.scanId, choiceId: choice.localId}]}); }
  catch { throw new Error('The survey page changed or Chrome lost access. Scan the current question again.'); }
  const result = results[0]?.result;
  if (!result?.ok) throw new Error(result?.reason || 'Could not circle that option. Scan again.');
  return result;
}

export async function removeCircles(tabId) {
  if (!Number.isInteger(tabId)) return;
  try { await chrome.scripting.executeScript({target: {tabId, allFrames: true}, func: clearCircle}); }
  catch { /* Navigation may already have removed the page and its circle. */ }
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(''))) return;
  if (!['scan', 'capture', 'circle', 'clear-circle'].includes(message?.type)) return;
  (async () => {
    try {
      const data = message.type === 'scan' ? await scan() : message.type === 'capture' ? await captureTab(message.tabId, message.windowId) : message.type === 'circle' ? await circleOption(message) : await removeCircles(message.tabId);
      reply({ok: true, data});
    } catch (error) { reply({ok: false, error: error.message || 'Could not read this tab.'}); }
  })();
  return true;
});
