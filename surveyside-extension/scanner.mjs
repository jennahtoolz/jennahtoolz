// Passed to chrome.scripting.executeScript: keep this function self-contained.
export function scanDocument() {
  globalThis.__surveysideScan?.cleanup?.();
  const scanId = crypto.randomUUID();
  const targets = new Map();
  const roots = [document];
  const chunks = [];
  let length = 0;
  let visited = 0;
  let truncated = false;
  const limit = 16000;
  function visible(element, allowInput = false) {
    if (!element || element.closest(`script,style,noscript,template,${allowInput ? '' : 'input,'}textarea,[data-surveyside-circle],[contenteditable]:not([contenteditable="false"]),[hidden],[aria-hidden="true"]`)) return false;
    if (!element.getClientRects().length) return false;
    for (let parent = element; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent);
      if (style.display === 'none' || style.visibility !== 'visible' || style.opacity === '0') return false;
    }
    return true;
  }
  function add(text) {
    text = text.replace(/\s+/g, ' ').trim();
    if (!text) return;
    const remaining = limit - length;
    if (remaining <= 0) { truncated = true; return; }
    chunks.push(text.slice(0, remaining));
    length += Math.min(text.length, remaining) + 1;
    if (text.length > remaining) truncated = true;
  }
  function read(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let node;
    while ((node = walker.nextNode())) {
      if (++visited > 12000 || length >= limit) { truncated = true; break; }
      if (node.nodeType === Node.TEXT_NODE && visible(node.parentElement)) add(node.textContent);
      else if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'SELECT' && visible(node)) add('Dropdown choices: ' + [...node.options].filter(option => !option.hidden).map(option => option.textContent.trim()).join(' / '));
      else if (node.nodeType === Node.ELEMENT_NODE && node.shadowRoot && visible(node)) { roots.push(node.shadowRoot); read(node.shadowRoot); }
    }
  }
  if (document.body) read(document.body);
  const choices = [];
  const seen = new Set();
  const clean = text => (text || '').replace(/\s+/g, ' ').trim();
  function safeText(element, max = 500) {
    if (!element) return '';
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const parts = [];
    let node, count = 0, size = 0;
    while ((node = walker.nextNode()) && ++count < 1000 && size < max) {
      if (visible(node.parentElement)) { const text = clean(node.textContent); parts.push(text); size += text.length + 1; }
    }
    return parts.join(' ').slice(0, max);
  }
  for (const root of roots) {
    for (const control of root.querySelectorAll('input[type="radio"],input[type="checkbox"],[role="radio"],[role="checkbox"],[role="option"],select,button')) {
      if (choices.length >= 100 || control.disabled || control.matches(':disabled') || control.getAttribute('aria-disabled') === 'true') continue;
      const native = control.matches('input');
      const target = native ? [...(control.labels || [])].find(element => visible(element)) || control.closest('label') || control : control;
      if (!target || !visible(target, true) || seen.has(target)) continue;
      const labelled = control.getAttribute('aria-labelledby')?.split(/\s+/).map(id => root.getElementById(id)?.textContent || '').join(' ');
      const label = clean(control.getAttribute('aria-label') || labelled || (control.matches('select') ? safeText(control.labels?.[0]) || 'Dropdown' : safeText(target, 241)) || target.querySelector('img')?.alt);
      if (!label || label.length > 240) continue;
      if (control.matches('button') && (control.type === 'submit' || /^(next|continue|back|previous|submit|finish|start|cancel|log ?in|sign ?in)(\b|$)/i.test(label))) continue;
      seen.add(target);
      const group = control.closest('fieldset,[role="radiogroup"],[role="group"]') || target.parentElement;
      const context = safeText(group);
      if (control.matches('select')) {
        for (const option of control.options) {
          if (option.disabled || option.hidden || !clean(option.textContent) || choices.length >= 100) continue;
          const id = crypto.randomUUID();
          const item = {id, label: clean(option.textContent).slice(0, 240), kind: 'dropdown', context};
          choices.push(item); targets.set(id, {element: target, control, label: item.label, option});
        }
      } else {
        const id = crypto.randomUUID();
        const item = {id, label, kind: native ? control.type : control.getAttribute('role') || 'button', context};
        choices.push(item); targets.set(id, {element: target, control, label, option: null});
      }
    }
  }
  const snapshotNow = () => roots.map(root => safeText(root === document ? document.body : root, 24000)).join('\n');
  globalThis.__surveysideScan = {scanId, targets, roots, page: location.href, snapshotNow, snapshot: snapshotNow(), cleanup: null};
  const origins = new Set();
  for (const frame of document.querySelectorAll('iframe[src]')) {
    try {
      const url = new URL(frame.src, location.href);
      if (['http:', 'https:'].includes(url.protocol) && url.origin !== location.origin && frame.getClientRects().length) origins.add(url.origin + '/*');
    } catch { /* Ignore invalid or non-web frame sources. */ }
  }
  return {title: document.title.slice(0, 160), origin: location.origin, text: chunks.join('\n'), truncated, frameOrigins: [...origins], scanId, choices};
}
