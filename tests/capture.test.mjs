import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
function compile(name, dependencies = {}) {
  const source = readFileSync(new URL(`../src/capture/${name}.ts`, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => dependencies[id] ?? require(id), module, module.exports)
  return module.exports
}
const types = compile('types')
const { createCaptureController } = compile('controller', { './types': types })
const screen = { id: 'screen-token', kind: 'screen', title: 'Display 1', width: 1920, height: 1080, x: -1920, y: 0, primary: false }
const windowSource = { ...screen, id: 'window-token', kind: 'window', title: 'Learning notes' }
const result = { source: screen, width: 1920, height: 1080, format: 'image/png', capturedAt: 100, imageBase64: 'fixture' }
function setup(overrides = {}) {
  const calls = []
  const controller = createCaptureController({ listSources: async () => [screen, windowSource], capture: async source => { calls.push(source); return { ...result, source } }, ...overrides })
  return { controller, calls }
}
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }

test('discovery never selects or captures automatically; type changes clear selection', async () => {
  const { controller, calls } = setup()
  await controller.open()
  assert.equal(controller.getSnapshot().phase, 'selecting')
  assert.equal(controller.getSnapshot().selected, null)
  controller.select(screen)
  controller.chooseKind('window')
  assert.equal(controller.getSnapshot().selected, null)
  controller.select(screen)
  assert.equal(controller.getSnapshot().selected, null)
  controller.select(windowSource)
  assert.equal(controller.getSnapshot().selected, windowSource)
  assert.equal(calls.length, 0)
})
test('successful capture, retake and change source replace one result without history', async () => {
  const { controller, calls } = setup()
  await controller.open(); controller.select(screen); await controller.capture()
  assert.equal(controller.getSnapshot().phase, 'preview')
  assert.equal(controller.getSnapshot().result.format, 'image/png')
  await controller.retake(); assert.equal(calls.length, 2)
  await controller.open(); controller.chooseKind('window'); controller.select(windowSource); await controller.capture()
  assert.equal(controller.getSnapshot().result.source.kind, 'window')
  controller.clear(); assert.equal(controller.getSnapshot().result, null)
})
test('structured source-disappeared error returns to source picker without fake preview', async () => {
  const { controller } = setup({ capture: async () => { throw { code: 'source_unavailable', message: 'Choose it again.' } } })
  await controller.open(); controller.select(screen); await controller.capture()
  assert.equal(controller.getSnapshot().phase, 'selecting')
  assert.equal(controller.getSnapshot().error.code, 'source_unavailable')
  assert.equal(controller.getSnapshot().selected, null)
  assert.equal(controller.getSnapshot().result, null)
})
test('cancel discards an in-flight frame; repeated capture cannot start another operation', async () => {
  const pending = deferred(); let calls = 0
  const { controller } = setup({ capture: () => { calls++; return pending.promise } })
  await controller.open(); controller.select(screen)
  const operation = controller.capture(); await controller.capture()
  assert.equal(controller.getSnapshot().phase, 'capturing'); assert.equal(calls, 1)
  controller.cancel(); pending.resolve(result); await operation
  assert.equal(controller.getSnapshot().phase, 'idle'); assert.equal(controller.getSnapshot().result, null)
})
test('cancel discovery ignores stale replies and reopening starts fresh', async () => {
  const pending = deferred()
  const { controller } = setup({ listSources: () => pending.promise })
  const opening = controller.open(); controller.cancel(); pending.resolve([screen]); await opening
  assert.equal(controller.getSnapshot().phase, 'idle'); assert.equal(controller.getSnapshot().sources.length, 0)
})
test('region is a typed unsupported option and never invokes capture', async () => {
  const { controller, calls } = setup()
  await controller.open(); controller.chooseKind('region'); await controller.capture()
  assert.equal(calls.length, 0); assert.equal(controller.getSnapshot().selected, null)
})
test('unknown native errors are sanitized; subscribers clean up', async () => {
  const { controller } = setup({ listSources: async () => { throw 'internal path/secret' } })
  let updates = 0; const unsubscribe = controller.subscribe(() => updates++)
  await controller.open(); assert.equal(controller.getSnapshot().error.code, 'native_unavailable')
  assert.ok(!controller.getSnapshot().error.message.includes('secret'))
  unsubscribe(); controller.cancel(); assert.equal(updates, 2)
})
test('cancelling Change Source preserves the current preview and permits Retake', async () => {
  const { controller, calls } = setup()
  await controller.open(); controller.select(screen); await controller.capture()
  await controller.open(); controller.cancel()
  assert.equal(controller.getSnapshot().phase, 'preview')
  assert.equal(controller.getSnapshot().result.source.id, screen.id)
  await controller.retake(); assert.equal(calls.length, 2)
})


