import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
function compile(path, dependencies = {}) {
  const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => dependencies[id] ?? require(id), module, module.exports)
  return module.exports
}
const types = compile('vision/types.ts')
const { createObservationController } = compile('vision/controller.ts')
const { readQuestion } = compile('vision/client.ts', { './types': types })
const capture = { source: { id: 'source', kind: 'screen' }, width: 24, height: 16, format: 'image/png', capturedAt: 0, imageBase64: 'synthetic-fixture' }
const observation = {
  status: 'detected', question_type: 'multiple_choice', question_text: 'Which symbol appears in the diagram?',
  options: [{ label: 'A', text: 'Circle' }, { label: 'B', text: 'Square' }], instructions: ['Choose one answer.'],
  required_selection_count: 1, visible_context: [], visual_elements: [], extraction_confidence: .94, warnings: [],
}
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }

test('reading requires an explicit action, prevents duplicates and publishes only observations', async () => {
  const pending = deferred(); let calls = 0
  const controller = createObservationController(async () => { calls++; return pending.promise })
  assert.equal(calls, 0)
  const reading = controller.read(capture); await controller.read(capture)
  assert.equal(controller.getSnapshot().phase, 'reading'); assert.equal(calls, 1)
  pending.resolve(observation); await reading
  assert.deepEqual(controller.getSnapshot().observation, observation)
  assert.equal(controller.getSnapshot().phase, 'ready')
})
test('cancel/reset aborts transport and discards late results after retake/clear', async () => {
  const pending = deferred(); let signal
  const controller = createObservationController(async (_, incoming) => { signal = incoming; return pending.promise })
  const reading = controller.read(capture); controller.reset()
  assert.equal(signal.aborted, true)
  pending.resolve(observation); await reading
  assert.equal(controller.getSnapshot().phase, 'idle'); assert.equal(controller.getSnapshot().observation, null)
})
test('errors permit an explicit retry; successful no-question and unclear responses remain honest', async () => {
  let fail = true
  const controller = createObservationController(async () => { if (fail) throw { code: 'provider_timeout', message: 'Please retry.' }; return { ...observation, status: 'unclear', warnings: ['Option B is cropped.'] } })
  await controller.read(capture); assert.equal(controller.getSnapshot().error.code, 'provider_timeout')
  fail = false; await controller.read(capture)
  assert.equal(controller.getSnapshot().phase, 'ready'); assert.equal(controller.getSnapshot().observation.status, 'unclear')
  controller.reset(); assert.equal(controller.getSnapshot().observation, null)
})
test('runtime boundary rejects malformed, extra-answer and inconsistent results', () => {
  assert.deepEqual(types.parseObservation(observation), observation)
  for (const patch of [{ correct_answer: 'A' }, { question_type: 'made_up' }, { extraction_confidence: 2 }, { status: 'detected', question_text: null }, { options: [{ label: 'A', text: 'One' }, { label: 'A', text: 'Two' }] }]) {
    assert.throws(() => types.parseObservation({ ...observation, ...patch }))
  }
  const empty = { ...observation, status: 'no_question', question_type: 'unknown', question_text: null, options: [], required_selection_count: null, warnings: ['No visible question.'] }
  assert.equal(types.parseObservation(empty).status, 'no_question')
})
test('transport sends only the capture image on request, without cookies, source titles or provider keys', async t => {
  let request
  t.mock.method(globalThis, 'fetch', async (url, init) => { request = { url, init }; return { ok: true, json: async () => observation } })
  const result = await readQuestion(capture, new AbortController().signal)
  assert.deepEqual(result, observation)
  assert.equal(request.url, 'http://127.0.0.1:8000/api/v1/vision/question')
  assert.deepEqual(JSON.parse(request.init.body), { media_type: 'image/png', image_base64: capture.imageBase64 })
  assert.equal(request.init.credentials, 'omit'); assert.equal(request.init.cache, 'no-store'); assert.equal(request.init.redirect, 'error')
  assert.equal('Authorization' in request.init.headers, false)
})
test('backend errors and network failures are user friendly and sanitized', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, json: async () => ({ error: { code: 'provider_authentication', message: 'private provider internals' } }) }))
  await assert.rejects(readQuestion(capture, new AbortController().signal), error => error.code === 'provider_authentication' && !error.message.includes('private'))
  globalThis.fetch.mock.mockImplementation(async () => { throw new TypeError('connection failed') })
  await assert.rejects(readQuestion(capture, new AbortController().signal), error => error.code === 'backend_unavailable')
})
test('oversized captures fail before network transmission', async t => {
  const fetch = t.mock.method(globalThis, 'fetch', async () => { throw Error('must not call') })
  await assert.rejects(readQuestion({ ...capture, imageBase64: 'x'.repeat(14 * 1024 * 1024) }, new AbortController().signal), error => error.code === 'image_too_large')
  assert.equal(fetch.mock.callCount(), 0)
})
test('observation presentation preserves options/code and escapes untrusted text without answer highlights', () => {
  const { QuestionObservationView } = compile('components/QuestionObservationView.tsx')
  const React = require('react'); const { renderToStaticMarkup } = require('react-dom/server')
  const observed = { ...observation, visual_elements: [{ kind: 'code', description: 'Visible snippet.', language: 'python', text: 'if flag:\n    x = 1' }], warnings: ['<script>unsafe()</script>'] }
  const html = renderToStaticMarkup(React.createElement(QuestionObservationView, { state: { phase: 'ready', observation: observed, error: null }, onRetry() {}, onCancel() {} }))
  assert.ok(html.includes('QUESTION DETECTED') && html.includes('Circle') && html.includes('Square'))
  assert.ok(html.includes('if flag:\n    x = 1'))
  assert.ok(html.includes('&lt;script&gt;') && !html.includes('<script>'))
  assert.ok(!html.includes('correct-answer') && !html.includes('recommended'))
})
