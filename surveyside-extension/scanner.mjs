// Passed to chrome.scripting.executeScript: keep this function self-contained.
export function scanDocument() {
  const chunks = [];
  let length = 0;
  let visited = 0;
  let truncated = false;
  const limit = 16000;
  function visible(element) {
    if (!element || element.closest('script,style,noscript,template,input,textarea,[contenteditable]:not([contenteditable="false"]),[hidden],[aria-hidden="true"]')) return false;
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
      else if (node.nodeType === Node.ELEMENT_NODE && node.shadowRoot && visible(node)) read(node.shadowRoot);
    }
  }
  if (document.body) read(document.body);
  const origins = new Set();
  for (const frame of document.querySelectorAll('iframe[src]')) {
    try {
      const url = new URL(frame.src, location.href);
      if (['http:', 'https:'].includes(url.protocol) && url.origin !== location.origin && frame.getClientRects().length) origins.add(url.origin + '/*');
    } catch { /* Ignore invalid or non-web frame sources. */ }
  }
  return {title: document.title.slice(0, 160), origin: location.origin, text: chunks.join('\n'), truncated, frameOrigins: [...origins]};
}
