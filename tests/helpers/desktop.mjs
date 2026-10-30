// Synthetic, offline presentation states. No account, capture or provider transport.
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import ts from 'typescript'
const require = createRequire(import.meta.url)
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const noop = () => {}
const h = React.createElement
function compile(file, dependencies = {}) {
  const source = readFileSync(new URL(`../../src/${file}`, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => dependencies[id] ?? require(id), module, module.exports)
  return module.exports
}
export const user = { id: 'fixture', email: 'learner@example.com', display_name: 'Practice learner', avatar_url: null }
export const observation = { status: 'detected', question_type: 'multiple_choice', question_text: 'Which tool automates a business process without writing code?', instructions: ['Choose one answer.'], options: [{ label: 'A', text: 'Flow' }, { label: 'B', text: 'Apex' }], required_selection_count: 1, visible_context: ['A declarative solution is required.'], visual_elements: [], extraction_confidence: .93, warnings: ['Review the original capture for accuracy.'] }
export const recommendation = { status: 'answered', question_type: 'multiple_choice', selected_options: ['A'], answer_text: null, true_false_answer: null, code_answer: null, explanation: 'Flow provides declarative automation for this practice example.', key_points: ['Use the stated requirement to compare the available tools.'], confidence: .86, warnings: [], grounding: { grounding_status: 'document_supported', reasoning_mode: 'materials_only', retrieval_method: 'lexical', citations: [{ chunk_id: 'chunk', document_id: 'document', document_title: 'Practice automation reference', page_number: 2, location: 'Page 2', excerpt: 'Flow supports declarative business automation.', supports: ['answer', 'explanation'] }], general_reasoning: [] } }
export const document = { id: 'document', title: 'Practice automation reference', document_type: 'pdf', extraction_status: 'ready', source_type: 'upload', original_filename: 'practice.pdf', character_count: 48, created_at: '2026-10-28T10:00:00Z', extracted_text: 'Flow supports declarative business automation.', extraction_structure: [{ kind: 'page', number: 2, start: 0, end: 48 }] }
const Brand = compile('components/Brand.tsx')
const Account = compile('components/AccountPanel.tsx', { '../auth/context': {} })
const Privacy = compile('components/PrivacySettings.tsx', { '../privacy/controller': {}, '../privacy/native': {} })
export const Views = {
  ...compile('components/QuestionObservationView.tsx'),
  ...compile('components/AnswerRecommendationView.tsx'),
  ...compile('components/ReasoningControls.tsx'),
  ...compile('components/ContextLibrary.tsx', { '../auth/context': {}, '../library/client': {}, '../library/controller': {} }),
  ...compile('components/CaptureDialog.tsx'),
  ...Privacy,
}
const authLogic = compile('auth/controller.ts')
const captureResult = { source: { kind: 'window', title: 'Disposable practice question' }, width: 600, height: 360, format: 'image/svg+xml', capturedAt: 0, imageBase64: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="360"><rect width="600" height="360" fill="#fff"/><text x="30" y="80" font-family="sans-serif" font-size="22">Practice question</text><text x="30" y="130" font-family="sans-serif" font-size="16">Which tool automates without code?</text><text x="30" y="190" font-family="sans-serif" font-size="18">A. Flow</text><text x="30" y="230" font-family="sans-serif" font-size="18">B. Apex</text></svg>').toString('base64') }
const stub = snapshot => ({ getSnapshot: () => snapshot, subscribe: () => noop, ready: () => true, options: () => ({}), reset: noop, dispose: noop })
export function desktopFixture(kind = 'workspace') {
  const state = { phase: kind === 'auth' ? 'signed_out' : 'signed_in', user: kind === 'auth' ? null : user, message: null }
  const authContext = { useAuth: () => ({ state, controller: {} }), AuthProvider: ({ children }) => children }
  const AccountPanel = () => h(Account.AccountContent, { state, onSignIn: noop, onSignOut: noop, onCancel: noop, onRefresh: noop })
  const gate = compile('components/AuthGate.tsx', { '../auth/controller': authLogic, './AccountPanel': { AccountPanel }, './Brand': Brand })
  const privacyProps = { state: { phase: 'ready', message: null, status: { preferenceEnabled: true, effectiveState: 'enabled', supported: true, preferencePersisted: true } }, onSet: noop, onRetry: noop }
  const settings = compile('components/SettingsDialog.tsx', { './AccountPanel': { AccountPanel }, './PrivacySettings': { PrivacySettings: () => h(Privacy.PrivacyContent, privacyProps) } })
  const reasoningState = { mode: 'materials_only', selected: ['document'], consent: !['consent', 'empty', 'loading'].includes(kind), embeddingConsent: false, busy: false, error: null, catalog: { documents: [{ ...document, index_status: 'ready', method: 'lexical' }], semantic_available: false } }
  const answerState = ['empty', 'loading', 'consent'].includes(kind) ? { phase: 'idle', error: null, result: null } : kind === 'error' ? { phase: 'error', error: { message: 'The provider timed out. You can try again.' }, result: null } : kind === 'insufficient' ? { phase: 'ready', error: null, result: { ...recommendation, status: 'insufficient_information', selected_options: [], confidence: 0, explanation: 'The selected material does not support a reliable answer.', key_points: [], grounding: { ...recommendation.grounding, grounding_status: 'insufficient_evidence', citations: [] } } } : { phase: 'ready', error: null, result: recommendation }
  const workspace = compile('components/AnswerWorkspace.tsx', {
    react: { ...React, useSyncExternalStore: (_subscribe, snapshot) => snapshot() },
    '../auth/context': authContext, '../auth/client': {}, '../auth/workspace': { authenticatedCapture: () => ({}), connectWorkspaceAccess: noop },
    '../capture/native': {}, '../capture/controller': { createCaptureController: () => stub({ phase: kind === 'empty' ? 'idle' : 'preview', kind: 'window', result: kind === 'empty' ? null : captureResult, sources: [], loading: false, selected: null }) },
    '../vision/controller': { createObservationController: () => stub({ phase: kind === 'empty' ? 'idle' : kind === 'loading' ? 'reading' : 'ready', observation: ['empty', 'loading'].includes(kind) ? null : observation, error: null }) }, '../vision/client': {},
    '../answer/controller': { createAnswerController: () => stub(answerState), connectAnswerLifecycle: noop }, '../answer/client': {},
    '../rag/controller': { createReasoningController: () => stub(reasoningState) }, '../rag/client': {}, '../library/changes': { subscribeLibraryChanges: () => noop },
    './LiveMonitor': { LiveMonitor: () => null },
    './CaptureDialog': { CaptureDialog: () => null }, './CapturePreview': compile('components/CapturePreview.tsx'),
    './QuestionObservationView': Views, './AnswerRecommendationView': Views, './ReasoningControls': Views,
  })
  const App = compile('App.tsx', {
    './auth/context': authContext, './auth/controller': authLogic, './components/AuthGate': gate,
    './components/LearningWorkspace': { LearningWorkspace: workspace.AnswerWorkspace }, './components/Sidebar': compile('components/Sidebar.tsx', { './Brand': Brand }),
    './components/ContextLibrary': {}, './components/SettingsDialog': { SettingsDialog: () => null }, './components/PointerLight': { PointerLight: () => null },
    './hooks/useTheme': { useTheme: () => ({ theme: 'dark', setTheme: noop }) }, './hooks/usePointerPreference': { usePointerPreference: () => ({ pointerLight: false, setPointerLight: noop }) },
  }).default
  if (kind === 'library') return renderToStaticMarkup(h(Views.LibraryContent, { state: { phase: 'ready', documents: [document], detail: document, limits: { upload_bytes: 10485760, text_characters: 500000, pdf_pages: 200 } }, controller: {}, onModalChange: noop }))
  if (kind === 'settings') return renderToStaticMarkup(h(settings.SettingsDialog, { open: true, theme: 'dark', setTheme: noop, pointerLight: true, setPointerLight: noop, onClose: noop })).replace('<dialog ', '<dialog open ')
  if (kind === 'capture') return renderToStaticMarkup(h(Views.CaptureDialog, { state: { phase: 'selecting', kind: 'window', sources: [{ id: 'practice', kind: 'window', title: 'Practice question — Sample application', width: 1920, height: 1080, x: 0, y: 0 }], selected: null, loading: false, error: null }, controller: {} })).replace('<dialog ', '<dialog open ')
  return renderToStaticMarkup(h(App))
}
