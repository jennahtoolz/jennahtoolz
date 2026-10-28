export async function summarizeFrames(results, hasPermission) {
  const frames = results.filter(item => item.result?.text);
  const missing = new Set();
  for (const {result} of results) {
    for (const origin of result?.frameOrigins || []) {
      if (!await hasPermission(origin)) missing.add(origin);
    }
  }
  const text = frames.map(({result}) => `--- ${result.title || 'Survey frame'} (${result.origin}) ---\n${result.text}`).join('\n\n');
  const choices = frames.flatMap(({frameId, documentId, result}) => (result.choices || []).map(choice => ({...choice,
    id: `f${frameId}:${choice.id}`, localId: choice.id, frameId, documentId, scanId: result.scanId}))).slice(0, 120);
  return {title: results.find(item => item.frameId === 0)?.result?.title || 'Survey page', text: text.slice(0, 24000),
    frameCount: frames.length, truncated: text.length > 24000 || frames.some(item => item.result.truncated), missingOrigins: [...missing], choices};
}
