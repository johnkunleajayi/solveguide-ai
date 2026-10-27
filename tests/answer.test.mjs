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
const types = compile('answer/types.ts')
const { createAnswerController, connectAnswerLifecycle } = compile('answer/controller.ts')
const captureTypes = compile('capture/types.ts')
const { createCaptureController } = compile('capture/controller.ts', { './types': captureTypes })
const { createObservationController } = compile('vision/controller.ts')
const { getSuggestedAnswer } = compile('answer/client.ts', { './types': types })
const observation = { status: 'detected', question_type: 'multiple_choice', question_text: 'Which figure is round?', options: [{ label: 'A', text: 'Circle' }, { label: 'B', text: 'Square' }], instructions: ['Choose one.'], required_selection_count: 1, visible_context: [], visual_elements: [], extraction_confidence: .95, warnings: [] }
const result = { status: 'answered', question_type: 'multiple_choice', selected_options: ['A'], answer_text: 'A circle.', true_false_answer: null, code_answer: null, explanation: 'A circle has no corners.', key_points: [], confidence: .88, warnings: [] }
const source = { id: 'screen', kind: 'screen', title: 'Display', width: 100, height: 100, x: 0, y: 0, primary: true }
const capture = { source, width: 100, height: 100, format: 'image/png', capturedAt: 0, imageBase64: 'synthetic' }
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }

test('Get Suggested Answer is explicit and double submission is blocked while loading', async () => {
  const pending = deferred(); let calls = 0
  const controller = createAnswerController(async () => { calls++; return pending.promise })
  assert.equal(calls, 0)
  const request = controller.request(observation); await controller.request(observation)
  assert.equal(controller.getSnapshot().phase, 'loading'); assert.equal(calls, 1)
  pending.resolve(result); await request
  assert.deepEqual(controller.getSnapshot().result, result)
})
test('failure and Try Again are manual and clear the previous recommendation', async () => {
  let calls = 0
  const controller = createAnswerController(async () => { if (++calls === 1) throw { code: 'answer_timeout', message: 'Try Again.' }; return result })
  await controller.request(observation)
  assert.equal(controller.getSnapshot().phase, 'error'); assert.equal(calls, 1)
  await controller.request(observation)
  assert.equal(controller.getSnapshot().phase, 'ready'); assert.equal(calls, 2)
})
for (const action of ['retake', 'change_source', 'clear', 'new_observation']) {
  test(`stale recommendations and late replies are invalidated after ${action}`, async () => {
    const captures = createCaptureController({ listSources: async () => [source], capture: async () => ({ ...capture }) })
    const observations = createObservationController(async () => ({ ...observation }))
    const pending = deferred(); let signal
    const answers = createAnswerController(async (_, s) => { signal = s; return pending.promise })
    const disconnect = connectAnswerLifecycle(answers, captures, observations)
    await captures.open(); captures.select(source); await captures.capture(); await observations.read(capture)
    const request = answers.request(observation)
    if (action === 'retake') await captures.retake()
    if (action === 'change_source') await captures.open()
    if (action === 'clear') captures.clear()
    if (action === 'new_observation') await observations.read(capture)
    assert.equal(signal.aborted, true)
    assert.equal(answers.getSnapshot().phase, 'idle')
    pending.resolve(result); await request
    assert.equal(answers.getSnapshot().result, null)
    disconnect()
  })
}
test('runtime validation rejects label/count/type mismatch and duplicate selections', () => {
  assert.deepEqual(types.parseAnswer(result, observation), result)
  for (const patch of [{ selected_options: ['Z'] }, { selected_options: ['A', 'B'] }, { selected_options: ['A', 'A'] }, { question_type: 'essay' }, { chain_of_thought: 'private' }, { confidence: 2 }]) {
    assert.throws(() => types.parseAnswer({ ...result, ...patch }, observation))
  }
  const multi = { ...observation, question_type: 'multiple_select', required_selection_count: 2 }
  assert.equal(types.parseAnswer({ ...result, question_type: 'multiple_select', selected_options: ['A', 'B'] }, multi).selected_options.length, 2)
  assert.throws(() => types.parseAnswer({ ...result, question_type: 'multiple_select' }, multi))
})
test('text-only transport sends observation, not a capture, credentials or automatic follow-up', async t => {
  let request
  t.mock.method(globalThis, 'fetch', async (url, init) => { request = { url, init }; return { ok: true, json: async () => result } })
  await getSuggestedAnswer(observation, new AbortController().signal)
  assert.equal(request.url, 'http://127.0.0.1:8000/api/v1/answer')
  assert.deepEqual(JSON.parse(request.init.body), observation)
  assert.ok(!request.init.body.includes('image_base64'))
  assert.equal(request.init.credentials, 'omit'); assert.equal(request.init.cache, 'no-store')
  assert.equal('Authorization' in request.init.headers, false)
})
test('provider/network errors are safe and permit explicit retry', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, json: async () => ({ error: { code: 'answer_authentication', message: 'secret upstream contents' } }) }))
  await assert.rejects(getSuggestedAnswer(observation, new AbortController().signal), error => error.code === 'answer_authentication' && !error.message.includes('secret'))
  globalThis.fetch.mock.mockImplementation(async () => { throw Error('network') })
  await assert.rejects(getSuggestedAnswer(observation, new AbortController().signal), error => error.code === 'backend_unavailable')
})
function render(answer, question = observation, phase = 'ready') {
  const { AnswerRecommendationView } = compile('components/AnswerRecommendationView.tsx')
  const React = require('react'); const { renderToStaticMarkup } = require('react-dom/server')
  return renderToStaticMarkup(React.createElement(AnswerRecommendationView, { state: { phase, result: answer, error: null }, observation: question, enabled: true, onRequest() {}, onCancel() {} }))
}
test('answer UI provides explicit action/loading and does not alter neutral observation', () => {
  assert.ok(render(null, observation, 'idle').includes('Get Suggested Answer'))
  assert.ok(render(null, observation, 'loading').includes('Cancel recommendation'))
  const html = render(result)
  assert.ok(html.includes('Recommended options') && html.includes('A circle.'))
  assert.ok(html.includes('Why') && html.includes('Answer confidence · 88%') && html.includes('reading confidence'))
  assert.equal(observation.options[0].correct, undefined)
})
test('multiple-select UI presents all recommended labels', () => {
  const html = render({ ...result, question_type: 'multiple_select', selected_options: ['A', 'B'] }, { ...observation, question_type: 'multiple_select', required_selection_count: 2 })
  assert.ok(html.includes('<strong>A</strong>') && html.includes('<strong>B</strong>'))
})
test('essay, mathematics and code preserve useful structure and escape provider HTML', () => {
  const essay = render({ ...result, question_type: 'essay', selected_options: [], answer_text: 'A thesis.', key_points: ['Supporting point.'] }, { ...observation, question_type: 'essay', options: [] })
  assert.ok(essay.includes('Suggested response') && !essay.includes('Recommended options'))
  const math = render({ ...result, question_type: 'mathematics', selected_options: [], answer_text: 'x = 3', key_points: ['2x = 6'] })
  assert.ok(math.includes('Explanation / key steps') && math.includes('x = 3'))
  const code = render({ ...result, question_type: 'code', selected_options: [], answer_text: '<script>unsafe()</script>', code_answer: { language: 'python', code: 'def add(a, b):\n    return a + b' } })
  assert.ok(code.includes('\n    return a + b') && code.includes('&lt;script&gt;') && !code.includes('<script>'))
})
test('uncertainty and abstention do not masquerade as definite answers', () => {
  assert.ok(render({ ...result, status: 'uncertain', warnings: ['Ambiguous choice.'] }).includes('TENTATIVE'))
  const html = render({ ...result, status: 'insufficient_information', selected_options: [], answer_text: null, confidence: 0, warnings: ['The graph is missing.'] })
  assert.ok(html.includes('MORE INFORMATION NEEDED') && !html.includes('Recommended options') && !html.includes('Answer confidence ·'))
})
