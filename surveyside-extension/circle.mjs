// Both functions run in the same Chrome isolated world as scanDocument.
export function clearCircle() {
  globalThis.__surveysideScan?.cleanup?.();
  return true;
}

export function drawCircle({scanId, choiceId}) {
  const state = globalThis.__surveysideScan;
  state?.cleanup?.();
  const choice = state?.scanId === scanId && state.targets.get(choiceId);
  const unchanged = () => state.page === location.href && state.snapshot === state.snapshotNow();
  if (!choice || !choice.element.isConnected || !choice.control.isConnected || !unchanged()) return {ok: false, reason: 'The question changed. Scan it again before circling an option.'};
  if (choice.control.disabled || choice.control.matches(':disabled') || choice.control.getAttribute('aria-disabled') === 'true') return {ok: false, reason: 'That option is no longer available. Scan again.'};
  if (choice.option && (!choice.option.isConnected || choice.option.disabled || choice.option.hidden || choice.option.textContent.replace(/\s+/g, ' ').trim() !== choice.label)) return {ok: false, reason: 'The dropdown changed. Scan it again.'};
  const host = document.createElement('div');
  host.dataset.surveysideCircle = 'true'; host.setAttribute('aria-hidden', 'true');
  host.style.cssText = 'all:initial!important;position:fixed!important;inset:0!important;pointer-events:none!important;z-index:2147483647!important;';
  const shadow = host.attachShadow({mode: 'open'});
  const ring = document.createElement('div');
  ring.style.cssText = 'position:absolute;box-sizing:border-box;border:4px solid #e97616;border-radius:50%;box-shadow:0 0 0 3px #fff,0 2px 12px #142b4255;pointer-events:none;';
  const badge = document.createElement('div');
  badge.textContent = choice.option ? `Choose: ${choice.label}` : 'Suggested match';
  badge.hidden = !choice.option;
  badge.style.cssText = 'position:absolute;max-width:calc(100vw - 16px);box-sizing:border-box;padding:4px 9px;border:1px solid #fff;border-radius:6px;background:#a83e00;color:#fff;font:600 12px/1.4 system-ui,sans-serif;overflow-wrap:anywhere;pointer-events:none;';
  shadow.append(ring, badge); document.documentElement.append(host);
  let timer, animation;
  const queue = () => { if (!animation) animation = requestAnimationFrame(update); };
  const cleanup = () => {
    host.remove(); observer.disconnect(); resizeObserver.disconnect(); clearTimeout(timer); cancelAnimationFrame(animation);
    window.removeEventListener('scroll', queue, true); window.removeEventListener('resize', queue);
    window.removeEventListener('pagehide', cleanup); window.removeEventListener('popstate', cleanup); window.removeEventListener('hashchange', cleanup);
    document.removeEventListener('change', cleanup, true); document.removeEventListener('keydown', escape, true);
    if (state.cleanup === cleanup) state.cleanup = null;
  };
  const escape = event => { if (event.key === 'Escape') cleanup(); };
  function update() {
    animation = 0;
    if (!choice.element.isConnected || !choice.control.isConnected || !unchanged()) { cleanup(); return; }
    const rect = choice.element.getBoundingClientRect();
    if (!rect.width || !rect.height || choice.control.matches(':disabled') || choice.control.getAttribute('aria-disabled') === 'true') { cleanup(); return; }
    for (let node = choice.element; node; node = node.parentElement || node.getRootNode().host) {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility !== 'visible' || style.opacity === '0') { cleanup(); return; }
    }
    Object.assign(ring.style, {left: `${rect.left - 9}px`, top: `${rect.top - 7}px`, width: `${Math.max(rect.width, 18) + 18}px`, height: `${Math.max(rect.height, 18) + 14}px`});
    Object.assign(badge.style, {left: `${Math.max(8, rect.left - 5)}px`, top: `${Math.max(3, rect.top - 34)}px`});
  }
  const observer = new MutationObserver(queue);
  const resizeObserver = new ResizeObserver(queue);
  state.cleanup = cleanup;
  observer.observe(document.body, {subtree: true, childList: true, characterData: true, attributes: true}); resizeObserver.observe(choice.element);
  window.addEventListener('scroll', queue, true); window.addEventListener('resize', queue);
  window.addEventListener('pagehide', cleanup); window.addEventListener('popstate', cleanup); window.addEventListener('hashchange', cleanup);
  document.addEventListener('change', cleanup, true); document.addEventListener('keydown', escape, true);
  timer = setTimeout(cleanup, 120000);
  choice.element.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'}); update();
  return host.isConnected ? {ok: true, label: choice.label, kind: choice.option ? 'dropdown' : 'option'} : {ok: false, reason: 'That option is hidden. Scan the current question again.'};
}
