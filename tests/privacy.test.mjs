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
const { parsePrivacyStatus } = compile('privacy/types.ts')
const { createPrivacyController } = compile('privacy/controller.ts')
const { PrivacyContent } = compile('components/PrivacySettings.tsx', { '../privacy/native': {}, '../privacy/controller': { createPrivacyController } })
const React = require('react')
const { renderToStaticMarkup } = require('react-dom/server')
const enabled = { supported: true, preferenceEnabled: true, effectiveState: 'enabled', preferencePersisted: true, issue: null }
const disabled = { ...enabled, preferenceEnabled: false, effectiveState: 'disabled' }
const failed = { ...enabled, effectiveState: 'failed', issue: 'apply_failed' }

test('native contract keeps requested preference separate from effective state', () => {
  assert.deepEqual(parsePrivacyStatus(enabled), enabled)
  assert.deepEqual(parsePrivacyStatus(failed), failed)
  for (const raw of [{ ...enabled, effectiveState: 'unknown' }, { ...enabled, supported: false }, { ...enabled, preferenceEnabled: false }, { ...enabled, issue: 'apply_failed' }]) assert.throws(() => parsePrivacyStatus(raw))
})
test('native transport invokes scoped commands and does not contact a backend or web protection API', async () => {
  const calls = []
  const { privacyApi } = compile('privacy/native.ts', { './types': { parsePrivacyStatus }, '@tauri-apps/api/core': { isTauri: () => true, invoke: async (command, args) => { calls.push([command, args]); return args?.enabled === false ? disabled : enabled } } })
  assert.deepEqual(await privacyApi.get(), enabled)
  assert.deepEqual(await privacyApi.set(false), disabled)
  assert.deepEqual(calls, [['privacy_get_state', undefined], ['privacy_set_enabled', { enabled: false }]])
})
test('browser-only preview honestly reports unsupported and never invokes protection', async () => {
  const { privacyApi } = compile('privacy/native.ts', { './types': { parsePrivacyStatus }, '@tauri-apps/api/core': { isTauri: () => false, invoke: () => { throw Error('Must not invoke') } } })
  assert.equal((await privacyApi.get()).effectiveState, 'unsupported')
})
test('settings reads native persisted OFF and ON without overwriting either on mount', async () => {
  for (const saved of [disabled, enabled]) {
    const controller = createPrivacyController({ get: async () => saved, set: () => { throw Error('Must not write while reading') } })
    await controller.refresh()
    assert.deepEqual(controller.getSnapshot().status, saved)
  }
})
test('toggle waits for native result and exposes failed enable honestly', async () => {
  const changes = []
  const controller = createPrivacyController({ get: async () => disabled, set: async value => { changes.push(value); return failed } })
  await controller.refresh(); await controller.setEnabled(true)
  assert.deepEqual(changes, [true])
  assert.equal(controller.getSnapshot().status.effectiveState, 'failed')
})
test('toggle serializes pending native changes and reflects successful disable', async () => {
  let finish; let calls = 0
  const controller = createPrivacyController({ get: async () => enabled, set: () => { calls++; return new Promise(resolve => { finish = resolve }) } })
  await controller.refresh()
  const pending = controller.setEnabled(false)
  await controller.setEnabled(true)
  assert.equal(calls, 1); assert.equal(controller.getSnapshot().phase, 'updating')
  finish(disabled); await pending
  assert.equal(controller.getSnapshot().status.effectiveState, 'disabled')
})
test('transport failure clears old success and ignores replies after disposal', async () => {
  const controller = createPrivacyController({ get: async () => enabled, set: async () => { throw Error('raw native details') } })
  await controller.refresh(); await controller.setEnabled(false)
  assert.equal(controller.getSnapshot().status, null)
  assert.doesNotMatch(controller.getSnapshot().message, /raw native/)
  let finish
  const late = createPrivacyController({ get: () => new Promise(resolve => { finish = resolve }) })
  const pending = late.refresh(); late.dispose(); finish(enabled); await pending
  assert.equal(late.getSnapshot().status, null)
})
test('Settings presents effective protection, storage errors and limitations with accessible controls', () => {
  const render = status => renderToStaticMarkup(React.createElement(PrivacyContent, { state: { phase: 'ready', status, message: null }, onSet() {}, onRetry() {} }))
  assert.match(render(enabled), /Windows affinity verified/)
  assert.match(render(disabled), /normal capture behavior/)
  const failure = render(failed)
  assert.match(failure, /Could not verify/); assert.doesNotMatch(failure, /Windows affinity verified/)
  assert.match(failure, /role="switch"/); assert.match(failure, /aria-describedby=/)
  assert.match(render({ ...enabled, preferencePersisted: false }), /could not be saved/)
  assert.match(render({ ...enabled, supported: false, effectiveState: 'unsupported', issue: 'unsupported_version' }), /Unavailable/)
  assert.match(render(enabled), /not a guarantee against every capture method/)
})
test('privacy setting does not write theme/pointer preferences or replace existing Settings controls', () => {
  const { SettingsDialog } = compile('components/SettingsDialog.tsx', { './AccountPanel': { AccountPanel: () => null }, './PrivacySettings': { PrivacySettings: () => React.createElement('span', null, 'Screen-share privacy') } })
  const html = renderToStaticMarkup(React.createElement(SettingsDialog, { open: false, onClose() {}, theme: 'dark', setTheme() {}, pointerLight: true, setPointerLight() {} }))
  for (const text of ['Screen-share privacy', 'Appearance', 'Light', 'Dark', 'System', 'Pointer light']) assert.match(html, new RegExp(text))
})
