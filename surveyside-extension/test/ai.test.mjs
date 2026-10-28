import assert from 'node:assert/strict';
import test from 'node:test';
import {buildRequest, explain} from '../ai.mjs';

test('request separates supplied facts and untrusted question, and includes the optional image', () => {
  const request = buildRequest({question: 'Purchased coffee in the past 7 days? Yes / No', facts: 'Bought coffee yesterday.', note: 'Which time window?', screenshot: 'data:image/png;base64,aGVsbG8='});
  assert.match(request.systemInstruction.parts[0].text, /Never invent/);
  assert.match(request.systemInstruction.parts[0].text, /untrusted survey data/);
  assert.match(request.contents[0].parts[0].text, /Bought coffee yesterday/);
  assert.deepEqual(request.contents[0].parts[1], {inlineData: {mimeType: 'image/png', data: 'aGVsbG8='}});
  assert.equal(buildRequest({question: 'Question only'}).contents[0].parts.length, 1);
});

test('empty capture and invalid image never reach the provider', async () => {
  let called = false;
  const request = async () => { called = true; };
  await assert.rejects(explain({key: 'fixture-key', question: ''}, request), /Scan a question/);
  await assert.rejects(explain({key: 'fixture-key', question: 'Question', screenshot: 'https://other.test/image'}, request), /screenshot is invalid/);
  await assert.rejects(explain({key: '', question: 'Question'}, request), /API key/);
  await assert.rejects(explain({key: 'fixture-key', model: '../../other?key=oops', question: 'Question'}, request), /model name/);
  assert.equal(called, false);
});

test('Gemini transport uses its fixed HTTPS host, puts the key only in a header and decodes text', async () => {
  const text = await explain({key: 'fixture-secret', question: 'Fixture question'}, async (url, options) => {
    assert.equal(url, 'https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent');
    assert.equal(options.headers['x-goog-api-key'], 'fixture-secret');
    assert.equal(options.body.includes('fixture-secret'), false);
    return Response.json({candidates: [{content: {parts: [{text: JSON.stringify({explanation: 'Choose the answer matching your facts.', choiceId: null})}]}}]});
  });
  assert.deepEqual(text, {explanation: 'Choose the answer matching your facts.', choiceId: null});
});

test('provider errors do not expose returned secrets or manufacture answers', async () => {
  for (const [status, expected] of [[403, /API restrictions/], [429, /usage or rate limit/], [503, /temporarily unavailable/]]) {
    await assert.rejects(explain({key: 'fixture-key', question: 'Question'}, async () => new Response('sensitive-provider-details', {status})), expected);
  }
  await assert.rejects(explain({key: 'fixture-key', question: 'Question'}, async () => Response.json({candidates: []})), /no explanation/);
  await assert.rejects(explain({key: 'fixture-key', question: 'Question'}, async () => { throw new Error('fixture-secret'); }), error => !error.message.includes('fixture-secret') && /connect/.test(error.message));
});

test('screenshot capture rejects tab changes before capture and discards a capture after a tab switch', async () => {
  let tab = {id: 7, windowId: 2, url: 'https://app.qmee.com/'};
  let captures = 0;
  let switchAfterCapture = false;
  globalThis.chrome = {
    sidePanel: {setPanelBehavior: async () => {}},
    runtime: {onMessage: {addListener() {}}},
    tabs: {
      query: async () => [tab],
      captureVisibleTab: async () => { captures++; if (switchAfterCapture) tab = {...tab, id: 99}; return 'data:image/png;base64,aGVsbG8='; }
    }
  };
  try {
    const {captureTab} = await import('../background.mjs');
    await assert.rejects(captureTab(8, 2), /active tab changed/);
    assert.equal(captures, 0);
    assert.match(await captureTab(7, 2), /^data:image\/png/);
    switchAfterCapture = true;
    await assert.rejects(captureTab(7, 2), /changed during capture/);
    assert.equal(captures, 2);
  } finally { delete globalThis.chrome; }
});

test('a restricted iframe does not prevent scanning the main page; missing host access is explicit', async () => {
  const targets = [];
  globalThis.chrome = {
    tabs: {query: async () => [{id: 7, windowId: 2, url: 'https://app.qmee.com/'}]},
    permissions: {contains: async () => false},
    scripting: {executeScript: async ({target}) => {
      targets.push(target);
      if (target.allFrames) throw new Error('Restricted child frame');
      return [{frameId: 0, result: {title: 'Fixture', origin: 'https://app.qmee.com', text: 'Fixture question', frameOrigins: ['https://survey.fixture.invalid/*']}}];
    }}
  };
  try {
    const {scan} = await import('../background.mjs');
    const captured = await scan();
    assert.match(captured.text, /Fixture question/);
    assert.equal(captured.tabId, 7);
    assert.deepEqual(captured.missingOrigins, ['https://survey.fixture.invalid/*']);
    assert.deepEqual(targets, [{tabId: 7, allFrames: true}, {tabId: 7}]);
  } finally { delete globalThis.chrome; }
});

test('only an exact captured option ID can be returned for circling', async () => {
  const input = {key: 'fixture', question: 'Fixture', choices: [{id: 'f2:known', label: 'Yes', kind: 'radio', context: 'Question', documentId: 'private-local-metadata'}]};
  const provider = choiceId => async () => Response.json({candidates: [{content: {parts: [{text: JSON.stringify({explanation: 'Fixture explanation.', choiceId})}]}}]});
  assert.equal((await explain(input, provider('f2:known'))).choiceId, 'f2:known');
  assert.equal((await explain(input, provider('f3:unknown'))).choiceId, null);
  assert.equal((await explain(input, provider(null))).choiceId, null);
  assert.equal(JSON.stringify(buildRequest(input)).includes('private-local-metadata'), false);
  await assert.rejects(explain(input, async () => Response.json({candidates: [{content: {parts: [{text: 'not JSON'}]}}]})), /No option was circled/);
});

test('circling targets the scanned document and refuses a different active tab', async () => {
  let tab = {id: 7, windowId: 2, url: 'https://app.qmee.com/'};
  const calls = [];
  globalThis.chrome = {
    tabs: {query: async () => [tab]},
    scripting: {executeScript: async input => { calls.push(input); return [{result: {ok: true, label: 'Yes'}}]; }}
  };
  try {
    const {circleOption} = await import('../background.mjs');
    const input = {tabId: 7, windowId: 2, choice: {frameId: 2, documentId: 'fixture-doc', localId: 'fixture-choice', scanId: 'fixture-scan'}};
    assert.equal((await circleOption(input)).label, 'Yes');
    assert.deepEqual(calls[0].target, {tabId: 7, documentIds: ['fixture-doc']});
    tab = {...tab, id: 99};
    await assert.rejects(circleOption(input), /active tab changed/);
    assert.equal(calls.length, 1);
  } finally { delete globalThis.chrome; }
});
