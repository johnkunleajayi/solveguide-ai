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
const React = require('react')
const { renderToStaticMarkup: render } = require('react-dom/server')
const logic = compile('auth/controller.ts')
const { authenticatedCapture, connectWorkspaceAccess } = compile('auth/workspace.ts', { './controller': logic })
const { createCaptureController } = compile('capture/controller.ts', { './types': compile('capture/types.ts') })
const { createObservationController } = compile('vision/controller.ts')
const { createAnswerController } = compile('answer/controller.ts')
const user = { id: 'user', email: 'user@example.com', display_name: 'Learner', email_verified: true, avatar_url: null }
const api = patch => ({ me: async () => user, start: async () => {}, poll: async () => user, cancel: async () => {}, logout: async () => {}, ...patch })
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }

test('app-level gate never mounts core controls before valid auth and keeps local Settings available', () => {
  let current; let mounts = 0
  const { AuthGate } = compile('components/AuthGate.tsx', { '../auth/controller': logic, './AccountPanel': { AccountPanel: () => React.createElement('button', null, 'Sign in with Google') }, './Brand': compile('components/Brand.tsx') })
  const App = compile('App.tsx', {
    './auth/context': { AuthProvider: ({ children }) => children, useAuth: () => ({ state: current }) },
    './auth/controller': logic, './components/AuthGate': { AuthGate },
    './components/LearningWorkspace': { LearningWorkspace: () => { mounts++; return React.createElement('button', null, 'Analyze Question') } },
    './components/Sidebar': { Sidebar: () => null },
    './components/ContextLibrary': { ContextLibrary: () => React.createElement('section', null, 'Private library') },
    './components/SettingsDialog': { SettingsDialog: () => React.createElement('aside', null, 'Screen-share privacy · Appearance · Pointer Light') },
    './components/PointerLight': { PointerLight: () => null },
    './hooks/useTheme': { useTheme: () => ({ theme: 'dark', setTheme() {} }) },
    './hooks/usePointerPreference': { usePointerPreference: () => ({ pointerLight: true, setPointerLight() {} }) },
  }).default
  for (const phase of ['checking', 'signed_out', 'signing_in', 'signing_out', 'unavailable', 'error']) {
    current = { phase, user: null, message: null }
    const html = render(React.createElement(App))
    assert.doesNotMatch(html, />Analyze Question</)
    assert.match(html, /Screen-share privacy/); assert.match(html, /Appearance/); assert.match(html, /Pointer Light/)
  }
  assert.equal(mounts, 0)
  current = { phase: 'signed_in', user, message: null }
  assert.match(render(React.createElement(App)), />Analyze Question</)
  assert.equal(mounts, 1)
})
test('pending startup and backend outage fail closed, retry validates backend identity', async () => {
  const pending = deferred()
  const auth = logic.createAuthController(api({ me: () => pending.promise }))
  const check = auth.check(); assert.equal(logic.workspaceAllowed(auth.getSnapshot()), false)
  pending.resolve(user); await check; assert.equal(logic.workspaceAllowed(auth.getSnapshot()), true)
  const offline = logic.createAuthController(api({ me: async () => { throw { code: 'backend_unavailable' } } }))
  await offline.check(); assert.equal(offline.getSnapshot().phase, 'unavailable'); assert.equal(logic.workspaceAllowed(offline.getSnapshot()), false)
})
test('logout closes access immediately and prevents rapid re-login while revocation is pending', async () => {
  const pending = deferred(); let starts = 0
  const auth = logic.createAuthController(api({ logout: () => pending.promise, start: async () => { starts++ } }))
  await auth.check(); const logout = auth.signOut()
  assert.equal(auth.getSnapshot().phase, 'signing_out'); assert.equal(logic.workspaceAllowed(auth.getSnapshot()), false)
  await auth.signIn(); assert.equal(starts, 0)
  pending.resolve(); await logout; assert.equal(auth.getSnapshot().phase, 'signed_out')
  await auth.signIn(); assert.equal(starts, 1); await auth.cancel()
})
test('expired/revoked provider responses and transport outages remove authenticated access', async () => {
  for (const code of ['sign_in_required', 'session_expired', 'session_revoked', 'invalid_session', 'backend_unavailable', 'database_unavailable']) {
    const auth = logic.createAuthController(api()); await auth.check()
    const captures = createCaptureController({ listSources: async () => [], capture: async () => {} })
    const observation = createObservationController(async () => { throw { code, message: 'safe' } })
    const answer = createAnswerController(async () => { throw { code, message: 'safe' } })
    const cleanup = connectWorkspaceAccess(captures, observation, answer, auth.invalidate)
    await observation.read({}); assert.equal(logic.workspaceAllowed(auth.getSnapshot()), false)
    await auth.check(); observation.reset()
    await answer.request({}); assert.equal(logic.workspaceAllowed(auth.getSnapshot()), false)
    cleanup()
  }
})
test('workspace disposal aborts requests and late replies cannot restore old learning data', async () => {
  const pendingRead = deferred(); const pendingAnswer = deferred()
  const captures = createCaptureController({ listSources: async () => [], capture: async () => {} })
  let readSignal, answerSignal
  const observed = createObservationController(async (_, signal) => { readSignal = signal; return pendingRead.promise })
  const answered = createAnswerController(async (_, signal) => { answerSignal = signal; return pendingAnswer.promise })
  const disconnect = connectWorkspaceAccess(captures, observed, answered, () => {})
  const read = observed.read({}); const answer = answered.request({})
  disconnect(); assert.ok(readSignal.aborted && answerSignal.aborted)
  pendingRead.resolve({ question_text: 'old' }); pendingAnswer.resolve({ answer_text: 'old' }); await Promise.all([read, answer])
  assert.equal(observed.getSnapshot().observation, null); assert.equal(answered.getSnapshot().result, null); assert.equal(captures.getSnapshot().result, null)
})
test('capture preflight validates current backend identity and abandoned preflight cannot capture', async () => {
  let calls = 0; let denied = 0
  const native = { listSources: async () => { calls++; return [] }, capture: async () => { calls++; return {} } }
  const signedOut = authenticatedCapture(native, { me: async () => null }, () => { denied++ })
  await assert.rejects(signedOut.listSources()); assert.equal(calls, 0); assert.equal(denied, 1)
  const valid = authenticatedCapture(native, { me: async () => user }, () => {})
  await valid.listSources(); await valid.capture({}); assert.equal(calls, 2)
  const pending = deferred()
  const abandoned = authenticatedCapture(native, { me: () => pending.promise }, () => {})
  const capture = abandoned.capture({}); abandoned.close(); pending.resolve(user)
  await assert.rejects(capture); assert.equal(calls, 2)
})
test('native AI transport carries payload/request ID only and propagates cancellation', async () => {
  const calls = []; const pending = deferred()
  const { requestCore } = compile('api/core.ts', { '@tauri-apps/api/core': { isTauri: () => true, invoke: async (command, args) => { calls.push({ command, args }); return command === 'ai_request' ? pending.promise : undefined } } })
  const cancel = new AbortController()
  const result = requestCore('answer', { question_text: 'practice' }, cancel.signal)
  cancel.abort(); await assert.rejects(result)
  assert.equal(calls[0].command, 'ai_request'); assert.equal(calls[1].command, 'ai_cancel')
  assert.equal(calls[0].args.requestId, calls[1].args.requestId)
  assert.deepEqual(Object.keys(calls[0].args).sort(), ['kind', 'payload', 'requestId'])
  pending.resolve({ ok: true, status: 200, data: {} })
})
test('unknown 401 codes normalize to auth failure; browser application transport is unavailable', async () => {
  const { requestCore } = compile('api/core.ts', { '@tauri-apps/api/core': { isTauri: () => true, invoke: async () => ({ ok: false, status: 401, error: { code: 'unexpected' } }) } })
  assert.equal((await requestCore('answer', {}, new AbortController().signal)).error.code, 'sign_in_required')
  const desktopOnly = compile('api/core.ts', { '@tauri-apps/api/core': { isTauri: () => false } })
  await assert.rejects(desktopOnly.requestCore('vision', {}, new AbortController().signal), e => e.code === 'desktop_required')
})
