import {scanDocument} from './scanner.mjs';
import {summarizeFrames} from './scan-results.mjs';

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

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || !sender.url?.startsWith(chrome.runtime.getURL(''))) return;
  if (!['scan', 'capture'].includes(message?.type)) return;
  (async () => {
    try {
      const data = message.type === 'scan' ? await scan() : await captureTab(message.tabId, message.windowId);
      reply({ok: true, data});
    } catch (error) { reply({ok: false, error: error.message || 'Could not read this tab.'}); }
  })();
  return true;
});
