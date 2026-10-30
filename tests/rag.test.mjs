import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
function compile(path, dependencies = {}) {
  const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => dependencies[id] ?? require(id), module, module.exports)
  return module.exports
}
const React = require('react')
const { renderToStaticMarkup: render } = require('react-dom/server')
const { createReasoningController } = compile('rag/controller.ts')
const answerTypes = compile('answer/types.ts')
const { createAnswerController } = compile('answer/controller.ts')
const { parseGroundedAnswer } = compile('rag/client.ts', { '../library/client': {}, '../answer/types': answerTypes })
const { ReasoningControls } = compile('components/ReasoningControls.tsx')
const { AnswerRecommendationView } = compile('components/AnswerRecommendationView.tsx')
const auth = compile('auth/controller.ts')
const noop = () => {}
const id = '00000000-0000-0000-0000-000000000001'
const doc = { id, title: 'Salesforce reference', extraction_status: 'ready', index_status: 'ready', method: 'lexical', error_code: null, generation: 'one' }
const catalog = documents => ({ documents, semantic_available: true, next_cursor: null })
const api = (patch = {}) => ({ list: async () => catalog([doc]), index: async () => {}, ...patch })
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }
const observation = { question_type: 'short_answer', options: [], required_selection_count: null }
const answer = { status: 'answered', question_type: 'short_answer', selected_options: [], answer_text: 'Flow.', true_false_answer: null, code_answer: null, explanation: 'Supported by the reference.', key_points: [], confidence: 0.8, warnings: [] }
const grounded = { ...answer, reasoning_mode: 'materials_only', grounding_status: 'document_supported', retrieval_method: 'lexical', citations: [{ document_id: id, document_title: 'Reference', chunk_id: id, page_number: null, location: 'paragraph 1', excerpt: 'Flow can automate a business process.', supports: ['answer', 'explanation'] }], general_reasoning: [] }
const options = { mode: 'materials_only', document_ids: [id], allow_context_transmission: true }
function html(controller) { return render(React.createElement(ReasoningControls, { state: controller.getSnapshot(), controller })) }

test('General is default and requires no documents or transmission consent', () => {
  const c = createReasoningController(api(), noop, noop)
  assert.equal(c.getSnapshot().mode, 'general'); assert.equal(c.ready(), true)
  assert.deepEqual(c.options(), { mode: 'general', document_ids: [], allow_context_transmission: false })
})
test('explicit document selection recommends Context Guided without overriding General', async () => {
  const c = createReasoningController(api(), noop, noop); await c.refresh(); c.select(id)
  assert.equal(c.getSnapshot().mode, 'general'); assert.match(html(c), /Context Guided is recommended/)
  c.setMode('materials_only'); assert.equal(c.getSnapshot().mode, 'materials_only')
  c.select(id); assert.equal(c.getSnapshot().mode, 'materials_only'); assert.equal(c.ready(), false)
})
test('grounded modes require ready selected documents and explicit passage consent', async () => {
  const c = createReasoningController(api(), noop, noop); await c.refresh()
  c.setMode('materials_only'); assert.equal(c.ready(), false)
  c.select(id); assert.equal(c.ready(), false)
  c.consent(true); assert.equal(c.ready(), true)
  c.consent(false); assert.equal(c.ready(), false)
})
test('document selection is bounded to five and supports explicit deselection', async () => {
  const c = createReasoningController(api(), noop, noop)
  for (let i = 0; i < 6; i++) c.select(String(i))
  assert.equal(c.getSnapshot().selected.length, 5); c.select('0'); assert.equal(c.getSnapshot().selected.length, 4)
})
test('empty library and unavailable semantic capability remain honest', async () => {
  const c = createReasoningController(api({ list: async () => ({ ...catalog([]), semantic_available: false }) }), noop, noop)
  await c.refresh(); const markup = html(c)
  assert.match(markup, /No materials found/); assert.match(markup, /Semantic retrieval is unavailable/)
  assert.match(markup, /Local lexical indexing remains available/)
})
test('indexing readiness, failed extraction and consent controls are accessible', async () => {
  const c = createReasoningController(api({ list: async () => catalog([{ ...doc, index_status: 'failed', error_code: 'embedding_timeout' }, { ...doc, id: 'other', extraction_status: 'insufficient', index_status: 'not_indexed' }]) }), noop, noop)
  await c.refresh(); const markup = html(c)
  assert.match(markup, /retry indexing/); assert.match(markup, /cannot index/)
  assert.match(markup, /<fieldset/); assert.match(markup, /type="radio"/); assert.match(markup, /I allow OpenAI/)
  assert.match(markup, /Semantic index/); assert.match(markup, /Index locally/)
})
test('index requests are explicit, carry consent and refresh readiness after completion', async () => {
  const calls = []; const c = createReasoningController(api({ index: async (...values) => calls.push(values) }), noop, noop)
  c.embeddingConsent(true); await c.index(id, true)
  assert.deepEqual(calls, [[id, 'semantic_pgvector', true, true]])
  c.embeddingConsent(false); await c.index(id, false)
  assert.deepEqual(calls[1], [id, 'lexical', false, true])
})
test('focus refresh cannot supersede an in-flight indexing operation', async () => {
  const pending = deferred(); let lists = 0
  const c = createReasoningController(api({ index: () => pending.promise, list: async () => { lists++; return catalog([doc]) } }), noop, noop)
  const indexing = c.index(id, false); assert.equal(c.getSnapshot().busy, true)
  await c.refresh(); assert.equal(lists, 0)
  pending.resolve(); await indexing; assert.equal(c.getSnapshot().busy, false); assert.equal(lists, 1)
})
test('selected documents beyond the first page retain correct readiness', async () => {
  const calls = []
  const c = createReasoningController(api({ list: async (cursor, selected) => { calls.push(selected); return selected ? catalog([doc]) : { ...catalog([]), next_cursor: 'next' } } }), noop, noop)
  c.select(id); c.setMode('materials_only'); c.consent(true); await c.refresh()
  assert.deepEqual(calls[1], [id]); assert.equal(c.ready(), true)
})
test('deleted documents become unavailable rather than broadening selection', async () => {
  const c = createReasoningController(api({ list: async () => catalog([]) }), noop, noop)
  c.select(id); c.setMode('materials_only'); c.consent(true); await c.refresh()
  assert.equal(c.ready(), false); assert.deepEqual(c.options().document_ids, [id])
  assert.match(html(c), /Unavailable document/); c.select(id); assert.equal(c.getSnapshot().selected.length, 0)
})
test('mode, selection, consent and reindex changes synchronously invalidate pending answers', async () => {
  const pending = deferred(); let signal
  const a = createAnswerController(async (_, s) => { signal = s; return pending.promise })
  const c = createReasoningController(api(), a.reset, noop)
  const task = a.request(observation); c.setMode('context_guided')
  assert.ok(signal.aborted); assert.equal(a.getSnapshot().result, null)
  pending.resolve(answer); await task; assert.equal(a.getSnapshot().result, null)
  let resets = 0; const d = createReasoningController(api(), () => { resets++ }, noop)
  d.select(id); d.consent(true); await d.index(id, false); assert.ok(resets >= 3)
})
test('refreshed generation changes invalidate stale citations', async () => {
  let generation = 'one'; let resets = 0
  const c = createReasoningController(api({ list: async () => catalog([{ ...doc, generation }]) }), () => { resets++ }, noop)
  await c.refresh(); c.select(id); const before = resets
  generation = 'two'; await c.refresh(); assert.ok(resets > before)
})
test('logout disposal removes selected documents and discards late readiness', async () => {
  const pending = deferred(); const c = createReasoningController(api({ list: () => pending.promise }), noop, noop)
  c.select(id); c.consent(true); c.embeddingConsent(true); const task = c.refresh(); c.dispose(); pending.resolve(catalog([doc])); await task
  assert.deepEqual(c.getSnapshot().selected, []); assert.equal(c.getSnapshot().consent, false); assert.deepEqual(c.getSnapshot().catalog.documents, [])
})
test('expired session fails closed through the existing authentication gate', async () => {
  const account = auth.createAuthController({ me: async () => ({ id: 'user' }) }); await account.check()
  const c = createReasoningController(api({ list: async () => { throw { code: 'session_expired' } } }), noop, account.invalidate)
  await c.refresh(); assert.equal(auth.workspaceAllowed(account.getSnapshot()), false)
})
test('grounded answer contract rejects cross-selection, fabricated fields and false insufficiency', () => {
  const result = parseGroundedAnswer(grounded, observation, options)
  assert.equal(result.grounding.citations[0].document_id, id)
  for (const value of [{ ...grounded, reasoning_mode: 'context_guided' }, { ...grounded, grounding_status: 'insufficient_evidence' }, { ...grounded, general_reasoning: ['outside knowledge'] }, { ...grounded, citations: [{ ...grounded.citations[0], document_id: 'other' }] }, { ...grounded, citations: [{ ...grounded.citations[0], page_number: -1 }] }]) assert.throws(() => parseGroundedAnswer(value, observation, options))
})
test('citation view shows actual excerpts, source navigation and ungrounded general reasoning separately', () => {
  const result = parseGroundedAnswer({ ...grounded, reasoning_mode: 'context_guided', grounding_status: 'mixed', general_reasoning: ['Additional model reasoning.'], citations: [{ ...grounded.citations[0], excerpt: '<script>not executable</script>' }] }, observation, { ...options, mode: 'context_guided' })
  const markup = render(React.createElement(AnswerRecommendationView, { state: { phase: 'ready', result }, observation, onRequest: noop, onCancel: noop, enabled: true, onOpenDocument: noop }))
  assert.match(markup, /Open source document/); assert.match(markup, /&lt;script&gt;/); assert.doesNotMatch(markup, /<script>/)
  assert.match(markup, /General model reasoning/); assert.match(markup, /Lexical retrieval/); assert.match(markup, /<details>/)
})
test('Materials Only insufficiency has no answer, no citations and no confidence claim', () => {
  const raw = { ...grounded, status: 'insufficient_information', answer_text: null, explanation: 'No relevant support.', confidence: 0, warnings: ['No relevant support.'], grounding_status: 'insufficient_evidence', citations: [] }
  const result = parseGroundedAnswer(raw, observation, options)
  const markup = render(React.createElement(AnswerRecommendationView, { state: { phase: 'ready', result }, observation, onRequest: noop, onCancel: noop, enabled: true }))
  assert.match(markup, /Insufficient document evidence/); assert.doesNotMatch(markup, /class="answer-confidence"/)
})
test('native indexing transport exposes no credentials, paths or arbitrary route', async () => {
  const calls = []
  const { ragApi } = compile('rag/client.ts', { '../answer/types': answerTypes, '../library/client': { request: async operation => { calls.push(operation); return operation.kind === 'index_list' ? catalog([doc]) : {} } } })
  await ragApi.index(id, 'lexical', false, true); await ragApi.list(undefined, [id])
  assert.deepEqual(calls[0], { kind: 'index', id, method: 'lexical', consent: false, force: true })
  assert.deepEqual(calls[1], { kind: 'index_list', cursor: null, selected: [id] })
})

test('General uses the original observation transport and grounded requests carry explicit selection only', async () => {
  const calls = []
  const { getSuggestedAnswer } = compile('answer/client.ts', {
    './types': answerTypes,
    '../rag/client': { parseGroundedAnswer },
    '../api/core': { requestCore: async (kind, payload) => { calls.push({ kind, payload }); return { ok: true, status: 200, data: 'mode' in payload ? grounded : answer } } },
  })
  await getSuggestedAnswer(observation, new AbortController().signal, { ...options, mode: 'general' })
  assert.deepEqual(calls[0], { kind: 'answer', payload: observation })
  await getSuggestedAnswer(observation, new AbortController().signal, options)
  assert.deepEqual(calls[1], { kind: 'answer', payload: { observation, ...options } })
  assert.deepEqual(Object.keys(calls[1].payload).sort(), ['allow_context_transmission', 'document_ids', 'mode', 'observation'])
})

test('selected-source changes synchronously clear answers and unsubscribe on logout', async () => {
  const { notifyLibraryChange, subscribeLibraryChanges } = compile('library/changes.ts')
  const a = createAnswerController(async () => answer)
  await a.request(observation)
  const unsubscribe = subscribeLibraryChanges(changed => { if (changed === id) a.reset() })
  notifyLibraryChange('unselected'); assert.equal(a.getSnapshot().result, answer)
  notifyLibraryChange(id); assert.equal(a.getSnapshot().result, null)
  unsubscribe(); await a.request(observation); notifyLibraryChange(id)
  assert.equal(a.getSnapshot().result, answer)
})


test('Context Guided can render clearly attributed general reasoning without citations', () => {
 const raw={...answer,reasoning_mode:'context_guided',grounding_status:'general_reasoning',retrieval_method:'lexical',citations:[],general_reasoning:['General model knowledge, not selected-document evidence.']}
 const result=parseGroundedAnswer(raw,observation,{...options,mode:'context_guided'})
 assert.equal(result.answer_text,answer.answer_text)
 assert.deepEqual(result.grounding.citations,[])
 const markup=render(React.createElement(AnswerRecommendationView,{state:{phase:'ready',result,error:null},observation,onRequest:noop,onCancel:noop,enabled:true}))
 assert.match(markup,/General reasoning · not document-supported/)
 assert.match(markup,/not selected-document evidence/)
 assert.doesNotMatch(markup,/Open source document/)
 for(const forged of [{...raw,citations:grounded.citations},{...raw,grounding_status:'document_supported'},{...raw,general_reasoning:[]}]) assert.throws(()=>parseGroundedAnswer(forged,observation,{...options,mode:'context_guided'}))
 assert.throws(()=>parseGroundedAnswer({...raw,reasoning_mode:'materials_only'},observation,options))
})
