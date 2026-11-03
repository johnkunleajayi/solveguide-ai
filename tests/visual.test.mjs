import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup: render } = require('react-dom/server')
function compile(file, deps = {}) {
  const output = ts.transpileModule(readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => deps[id] ?? require(id), module, module.exports)
  return module.exports
}
const vision = compile('vision/types.ts'), answers = compile('answer/types.ts')
const view = compile('components/AnswerRecommendationView.tsx')
const { parseObservation } = vision
const observation = {
  status: 'detected', question_type: 'visual_reasoning', question_text: 'Transform Original into Edited.',
  options: [], instructions: [], required_selection_count: null, visible_context: [], visual_elements: [], extraction_confidence: .9, warnings: [],
  visual_task: { kind: 'editing_prompt', image_count: 2, complete: true, direction: 'established', observed_changes: ['Study becomes Research.', 'Green becomes mint.', 'Move the circle right.'], images: [
    { identifier: 'Original', position: 'right', role: 'original', description: 'Green Study title; circle on left.' },
    { identifier: 'Edited', position: 'left', role: 'edited', description: 'Mint Research title; circle shifted right.' },
  ] },
}
const answer = { status: 'answered', question_type: 'visual_reasoning', answer_text: 'Change Study to Research in mint, move the circle right; preserve other elements.', selected_options: [], true_false_answer: null, code_answer: null, explanation: 'The labelled pair establishes the transformation.', key_points: [], confidence: .8, warnings: [] }
const state = { phase: 'ready', result: answer, error: null }
test('two-slide observation preserves original direction, subtle text/color/position changes', () => {
  const parsed = parseObservation(observation)
  assert.equal(parsed.visual_task.images[0].position, 'right')
  assert.equal(parsed.visual_task.observed_changes.length, 3)
  const html = render(React.createElement(view.AnswerRecommendationView, { state, observation, automatic: true }))
  assert.match(html, /Suggested Editing Prompt/); assert.match(html, /Copy Response/); assert.match(html, /preserve other elements/)
  assert.match(html, /not document evidence/)
  assert.throws(() => answers.parseAnswer({ ...answer, answer_text: null, code_answer: { language: null, code: 'not a prompt' } }, observation))
})
test('Copy Response writes exactly the generated text, handles clipboard denial', async () => {
  const copied = []
  assert.equal(await view.copyResponse(answer.answer_text, async value => { copied.push(value) }), true)
  assert.deepEqual(copied, [answer.answer_text])
  assert.equal(await view.copyResponse(answer.answer_text, async () => { throw Error('denied') }), false)
})
test('five-image choices retain positions/labels and reject fabricated or multiple odd selections', () => {
  const images = ['A', 'B', 'C', 'D', 'E'].map((id, i) => ({ identifier: id, position: `column ${i + 1}`, role: 'option', description: i === 2 ? 'Square' : 'Circle' }))
  const task = { ...observation.visual_task, kind: 'odd_one_out', direction: 'not_applicable', images, image_count: 5 }
  const obs = parseObservation({ ...observation, visual_task: task, options: images.map(i => ({ label: i.identifier, text: i.description })) })
  assert.equal(answers.parseAnswer({ ...answer, selected_options: ['C'] }, obs).selected_options[0], 'C')
  for (const labels of [['FAKE'], ['A', 'C']]) assert.throws(() => answers.parseAnswer({ ...answer, selected_options: labels }, obs))
  assert.throws(() => parseObservation({ ...obs, options: obs.options.slice(1) }))
  const html = render(React.createElement(view.AnswerRecommendationView, { state: { ...state, result: { ...answer, selected_options: ['C'] } }, observation: obs, automatic: true }))
  assert.match(html, /Suggested Selection/); assert.match(html, /Square/); assert.match(html, /Copy Response/)
})
test('ambiguity and incomplete task descriptions display honest extraction state', () => {
  const obs = parseObservation({ ...observation, status: 'unclear', warnings: ['Labels unreadable.'], visual_task: { ...observation.visual_task, direction: 'ambiguous', complete: false } })
  const { QuestionObservationView } = compile('components/QuestionObservationView.tsx')
  const html = render(React.createElement(QuestionObservationView, { state: { phase: 'ready', observation: obs } }))
  assert.match(html, /Incomplete or unreadable/); assert.match(html, /ambiguous/); assert.match(html, /Labels unreadable/)
  assert.throws(() => parseObservation({ ...observation, visual_task: { ...observation.visual_task, image_count: 5 } }))
  const { MonitorResult } = compile('components/MonitorResult.tsx', { './AnswerRecommendationView': view })
  const panel = render(React.createElement(MonitorResult, { snapshot: { mode: 'general', questionNumber: 1, generation: 2, observation: obs, answer: null } }))
  assert.match(panel, /original-to-edited direction are unclear/); assert.match(panel, /Labels unreadable/)
})
test('pattern and spot-difference rendering remains plain text and retains uncertainty', () => {
  const obs = { ...observation, visual_task: { ...observation.visual_task, kind: 'spot_difference', direction: 'not_applicable' } }
  const html = render(React.createElement(view.AnswerRecommendationView, { state: { ...state, result: { ...answer, status: 'uncertain', warnings: ['Possible rendering artifact.'], answer_text: '<script>not executable</script>' } }, observation: obs, automatic: true }))
  assert.match(html, /Visual Explanation/); assert.match(html, /Possible rendering artifact/); assert.doesNotMatch(html, /<script>/)
})
test('visual to MCQ to coding transitions keep strict type validation', () => {
  for (const type of ['visual_reasoning', 'multiple_choice', 'code']) {
    const obs = { ...observation, question_type: type, visual_task: type === 'visual_reasoning' ? observation.visual_task : null, options: type === 'multiple_choice' ? [{ label: 'A', text: 'One' }] : [] }
    const result = { ...answer, question_type: type, selected_options: type === 'multiple_choice' ? ['A'] : [] }
    assert.equal(answers.parseAnswer(result, parseObservation(obs)).question_type, type)
    assert.throws(() => answers.parseAnswer({ ...result, question_type: 'unknown' }, obs))
  }
})
test('Stop/session unmount discards late visual recommendations', async () => {
  const rag = compile('rag/client.ts', { '../library/client': {}, '../answer/types': answers })
  const types = compile('monitor/types.ts', { '../vision/types': vision, '../answer/types': answers, '../rag/client': rag })
  const { createMonitorController } = compile('monitor/controller.ts', { './types': types })
  let resolve
  const pending = new Promise(r => { resolve = r })
  const calls = []
  const c = createMonitorController(op => { calls.push(op.kind); return op.kind === 'start' ? pending : Promise.resolve(types.initialMonitor) })
  const starting = c.command({ kind: 'start', source_id: 'owned', source_kind: 'window', session_id: 'session', revision: 1 })
  c.dispose(true)
  resolve({ ...types.initialMonitor, phase: 'answer_ready', observation, answer, generation: 1 })
  await starting
  assert.equal(c.getSnapshot().snapshot.answer, null); assert.deepEqual(calls, ['start', 'stop'])
})

test('mixed-visual editing intent has a copy button and the actual click writes only the prompt', async () => {
  const obs = parseObservation({ ...observation, visual_task: { ...observation.visual_task, kind: 'mixed_visual', requested_output: 'editing_prompt', comparisons: [] } })
  assert.equal(obs.visual_task.kind, 'editing_prompt')
  const html = render(React.createElement(view.AnswerRecommendationView, { state, observation: obs, automatic: true }))
  assert.match(html, /Suggested Editing Prompt/); assert.match(html, /Copy Response/)
  const legacy = render(React.createElement(view.AnswerRecommendationView, { state, observation: { ...obs, visual_task: { ...obs.visual_task, kind: 'mixed_visual', requested_output: null } }, automatic: true }))
  assert.match(legacy, /Copy Response/) // Defensive fallback for the reported older mixed classification.
  const clickable = compile('components/AnswerRecommendationView.tsx', { react: { ...React, useState: () => ['', () => {}] } })
  function find(node, predicate) {
    if (!node || typeof node !== 'object') return null
    if (predicate(node)) return node
    for (const child of React.Children.toArray(node.props?.children)) {
      const match = find(child, predicate)
      if (match) return match
    }
    return null
  }
  const tree = clickable.AnswerRecommendationView({ state, observation: obs, automatic: true })
  const action = find(tree, node => typeof node.type === 'function' && node.type.name === 'CopyResponse')
  assert.ok(action)
  const button = find(action.type(action.props), node => node.type === 'button')
  const copied = [], original = Object.getOwnPropertyDescriptor(globalThis, 'navigator')
  try {
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { clipboard: { writeText: async text => { copied.push(text) } } } })
    button.props.onClick()
    await new Promise(resolve => setImmediate(resolve))
    assert.deepEqual(copied, [answer.answer_text])
    assert.ok(!copied[0].includes(answer.explanation))
  } finally {
    if (original) Object.defineProperty(globalThis, 'navigator', original)
    else delete globalThis.navigator
  }
})

test('comparison facts are inspectable and attempt numbers do not claim unique questions', () => {
  const comparisons = [{ element: 'Second chart bar', property: 'size', original: 'shorter', edited: 'taller', status: 'changed' }, { element: 'Chart bars', property: 'color', original: 'blue', edited: 'blue', status: 'unchanged' }]
  const obs = parseObservation({ ...observation, visual_task: { ...observation.visual_task, comparisons } })
  const { MonitorResult } = compile('components/MonitorResult.tsx', { './AnswerRecommendationView': view })
  const html = render(React.createElement(MonitorResult, { snapshot: { mode: 'general', questionNumber: 5, generation: 7, observation: obs, answer } }))
  assert.match(html, /Processing attempt 5/); assert.match(html, /Observed comparison facts/); assert.match(html, /Second chart bar/); assert.match(html, /unchanged/)
  assert.throws(() => parseObservation({ ...obs, visual_task: { ...obs.visual_task, comparisons: [...comparisons, comparisons[0]] } }))
})
