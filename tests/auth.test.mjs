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
const { createAuthController } = compile('auth/controller.ts')
const { parseUser } = compile('auth/types.ts')
const { AccountContent } = compile('components/AccountPanel.tsx', { '../auth/context': {} })
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const user = { id: 'user-id', email: 'learner@example.com', email_verified: true, display_name: 'Learner', avatar_url: null }
function setup(overrides = {}) {
  const calls = []; let scheduled
  const api = { me: async () => null, start: async () => { calls.push('start') }, poll: async () => user, cancel: async () => { calls.push('cancel') }, logout: async () => { calls.push('logout') }, ...overrides }
  const controller = createAuthController(api, fn => { scheduled = fn; return 1 }, () => { scheduled = null })
  return { api, calls, controller, poll: async () => { scheduled(); await new Promise(resolve => setImmediate(resolve)) } }
}
test('account starts checking and derives signed-out state from backend', async () => {
  const { controller } = setup()
  assert.equal(controller.getSnapshot().phase, 'checking')
  await controller.check(); assert.equal(controller.getSnapshot().phase, 'signed_out')
})
test('sign in explicitly opens system-browser transport, polls once, and displays returned user', async () => {
  const { controller, calls, poll } = setup()
  await controller.check(); assert.deepEqual(calls, [])
  await controller.signIn(); await controller.signIn()
  assert.deepEqual(calls, ['start']); assert.equal(controller.getSnapshot().phase, 'signing_in')
  await poll(); assert.deepEqual(controller.getSnapshot().user, user)
  assert.equal(controller.getSnapshot().phase, 'signed_in')
})
test('initial valid session and sign out use backend authority', async () => {
  const { controller, calls } = setup({ me: async () => user })
  await controller.check(); assert.equal(controller.getSnapshot().phase, 'signed_in')
  await controller.signOut(); assert.deepEqual(calls, ['logout']); assert.equal(controller.getSnapshot().user, null)
})
test('expired or revoked sessions become signed-out with a safe message', async () => {
  for (const code of ['session_expired', 'session_revoked', 'invalid_session']) {
    const { controller } = setup({ me: async () => { throw { code, message: 'sensitive raw exception' } } })
    await controller.check(); assert.equal(controller.getSnapshot().phase, 'signed_out')
    assert.doesNotMatch(controller.getSnapshot().message, /sensitive/)
  }
})
test('configuration errors are sanitized and can be retried explicitly', async () => {
  const { controller } = setup({ start: async () => { throw { code: 'database_not_configured' } } })
  await controller.signIn(); assert.equal(controller.getSnapshot().phase, 'error')
  assert.match(controller.getSnapshot().message, /DATABASE_URL/)
})
test('cancel clears polling and discards a late sign-in result', async () => {
  let complete
  const result = new Promise(resolve => { complete = resolve })
  const { controller, poll, calls } = setup({ poll: () => result })
  await controller.signIn(); await poll(); await controller.cancel(); complete(user)
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(controller.getSnapshot().phase, 'signed_out'); assert.equal(controller.getSnapshot().user, null)
  assert.deepEqual(calls, ['start', 'cancel'])
})
test('logout failure keeps access closed without falsely claiming remote revocation', async () => {
  const { controller } = setup({ me: async () => user, logout: async () => { throw Error('offline') } })
  await controller.check(); await controller.signOut()
  assert.equal(controller.getSnapshot().phase, 'unavailable'); assert.equal(controller.getSnapshot().user, null)
})
test('account UI renders semantic sign-in, cancel, user and sign-out states with escaped identity', () => {
  const render = state => renderToStaticMarkup(React.createElement(AccountContent, { state, onSignIn() {}, onSignOut() {}, onCancel() {}, onRefresh() {} }))
  assert.match(render({ phase: 'signed_out', user: null }), /Sign in with Google/)
  assert.match(render({ phase: 'signing_in', user: null }), /Cancel sign-in/)
  const html = render({ phase: 'signed_in', user: { ...user, display_name: '<script>bad()</script>' } })
  assert.match(html, /Sign out/); assert.match(html, /learner@example.com/); assert.doesNotMatch(html, /<script>/)
})
test('auth transport uses cookies or native commands, never browser-readable credential storage', () => {
  for (const path of ['auth/client.ts', 'auth/controller.ts', 'components/AccountPanel.tsx']) {
    assert.doesNotMatch(readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8'), /localStorage|sessionStorage|exchange_secret|session_token/)
  }
  assert.deepEqual(parseUser(user), user)
  assert.throws(() => parseUser({ ...user, email: 1 }))
})
