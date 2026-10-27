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
const types = compile('library/types.ts')
const { createLibraryController } = compile('library/controller.ts')
const authLogic = compile('auth/controller.ts')
const noop = () => {}
const document = { id: '00000000-0000-0000-0000-000000000001', title: 'Study notes', original_filename: 'study.txt', document_type: 'txt', source_type: 'upload', byte_size: 20, extraction_status: 'ready', extraction_error: null, character_count: 20, created_at: '2026-10-27T12:00:00Z', updated_at: '2026-10-27T12:00:00Z', extracted_text: '<script>notes</script>', extraction_structure: [{ kind: 'text', number: 1, start: 0, end: 20 }] }
const limits = { upload_bytes: 10485760, text_characters: 500000, pdf_pages: 200 }
function api(patch = {}) { return { list: async () => ({ documents: [], next_cursor: null }), limits: async () => limits, upload: async () => document, paste: async () => document, detail: async () => document, rename: async (_, title) => ({ ...document, title }), delete: async () => {}, ...patch } }
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes }); return { resolve, promise } }
const { LibraryContent } = compile('components/ContextLibrary.tsx', { '../auth/context': {}, '../library/client': {}, '../library/controller': { createLibraryController } })
const content = state => render(React.createElement(LibraryContent, { state, controller: createLibraryController(api(), noop), onModalChange: noop }))

test('library loads an authenticated list and configured limits', async () => {
  const controller = createLibraryController(api(), noop)
  assert.equal(controller.getSnapshot().phase, 'loading')
  await controller.load()
  assert.equal(controller.getSnapshot().phase, 'ready')
  assert.deepEqual(controller.getSnapshot().limits, limits)
})
test('empty state distinguishes persistent materials from ephemeral learning and unused AI context', async () => {
  const c = createLibraryController(api(), noop); await c.load()
  const html = content(c.getSnapshot())
  assert.match(html, /A place for what/); assert.match(html, /Current answers do not use/)
  assert.match(html, /Live captures, questions and answers remain ephemeral/)
  assert.match(html, /PDF · DOCX · TXT/); assert.match(html, /10 MiB/)
  assert.match(html, /Add document/); assert.match(html, /Paste text/)
})
test('native upload gets a processing state and new document preview', async () => {
  const pending = deferred(); let docs = []
  const c = createLibraryController(api({ upload: () => pending.promise, list: async () => ({ documents: docs, next_cursor: null }) }), noop)
  await c.load(); const task = c.upload()
  assert.equal(c.getSnapshot().phase, 'working'); assert.match(content(c.getSnapshot()), /Working with your document/)
  docs = [document]; pending.resolve(document); assert.equal(await task, true)
  assert.equal(c.getSnapshot().detail.id, document.id); assert.equal(c.getSnapshot().documents.length, 1)
})
test('file picker cancellation does not create a document or lose existing preview', async () => {
  const c = createLibraryController(api({ upload: async () => null }), noop)
  await c.load(); await c.select(document.id); await c.upload()
  assert.equal(c.getSnapshot().detail.id, document.id); assert.equal(c.getSnapshot().notice, 'File selection cancelled.')
})
test('paste submits only explicit title and text', async () => {
  let sent
  const c = createLibraryController(api({ paste: async (...args) => { sent = args; return document } }), noop)
  await c.load(); await c.paste('Reference notes', 'Private study text')
  assert.deepEqual(sent, ['Reference notes', 'Private study text']); assert.equal(c.getSnapshot().detail.id, document.id)
})
test('detail preview renders escaped selectable text without HTML execution', async () => {
  const c = createLibraryController(api(), noop); await c.load(); await c.select(document.id)
  const html = content(c.getSnapshot())
  assert.match(html, /Extracted document text/); assert.match(html, /&lt;script&gt;/); assert.doesNotMatch(html, /<script>/)
  assert.match(html, /readOnly|readonly/); assert.match(html, /Rename title/)
})
test('failed extraction and scanned PDF states are honest', async () => {
  for (const status of ['failed', 'insufficient', 'deleting']) {
    const c = createLibraryController(api({ detail: async () => ({ ...document, extraction_status: status, extracted_text: '' }) }), noop)
    await c.load(); await c.select(document.id)
    const html = content(c.getSnapshot())
    assert.match(html, status === 'failed' ? /could not be extracted safely/ : status === 'insufficient' ? /No machine-readable text/ : /Deletion has started/)
    assert.doesNotMatch(html, /aria-label="Extracted document text"/)
  }
})
test('rename updates both list and detail', async () => {
  const c = createLibraryController(api({ list: async () => ({ documents: [document], next_cursor: null }) }), noop)
  await c.load(); await c.rename(document.id, 'Renamed')
  assert.equal(c.getSnapshot().detail.title, 'Renamed'); assert.equal(c.getSnapshot().documents[0].title, 'Renamed')
})
test('delete confirmation describes permanent removal before an explicit action', async () => {
  const c = createLibraryController(api(), noop); await c.load(); await c.select(document.id)
  const html = content(c.getSnapshot())
  assert.match(html, /<dialog/); assert.match(html, /Delete this document/); assert.match(html, /Keep document/)
  assert.match(html, /stored original/); assert.match(html, /cannot be undone/)
})
test('successful deletion clears preview and refreshes list', async () => {
  let removed
  const c = createLibraryController(api({ delete: async id => { removed = id } }), noop)
  await c.load(); await c.select(document.id); await c.delete(document.id)
  assert.equal(removed, document.id); assert.equal(c.getSnapshot().detail, null)
  assert.match(c.getSnapshot().notice, /deleted/)
})
test('delete failure retains document and gives a retryable error', async () => {
  const c = createLibraryController(api({ delete: async () => { throw { code: 'storage_unavailable', message: 'Deletion pending. Retry removal.' } } }), noop)
  await c.load(); await c.select(document.id); assert.equal(await c.delete(document.id), false)
  assert.equal(c.getSnapshot().detail.id, document.id); assert.match(c.getSnapshot().error, /Retry/)
})
test('session expiry closes the shared auth gate', async () => {
  const user = { id: 'user', display_name: 'Learner' }
  const auth = authLogic.createAuthController({ me: async () => user }); await auth.check()
  const c = createLibraryController(api({ list: async () => { throw { code: 'session_expired' } } }), auth.invalidate)
  await c.load(); assert.equal(authLogic.workspaceAllowed(auth.getSnapshot()), false)
})
test('logout disposal suppresses stale documents and prevents a follow-up list request', async () => {
  const pending = deferred(); let lists = 0
  const c = createLibraryController(api({ upload: () => pending.promise, list: async () => { lists++; return { documents: [], next_cursor: null } } }), noop)
  await c.load(); const task = c.upload(); c.dispose(); pending.resolve(document); await task
  assert.equal(c.getSnapshot().detail, null); assert.deepEqual(c.getSnapshot().documents, []); assert.equal(lists, 1)
})
test('rapid duplicate mutations are ignored while a request is working', async () => {
  const pending = deferred(); let calls = 0
  const c = createLibraryController(api({ upload: () => { calls++; return pending.promise } }), noop)
  await c.load(); const first = c.upload(); await c.upload(); assert.equal(calls, 1)
  pending.resolve(null); await first
})
test('pagination appends documents instead of replacing the current page', async () => {
  const second = { ...document, id: '00000000-0000-0000-0000-000000000002' }
  const c = createLibraryController(api({ list: async cursor => ({ documents: cursor ? [second] : [document], next_cursor: cursor ? null : 'cursor' }) }), noop)
  await c.load(); await c.more(); assert.equal(c.getSnapshot().documents.length, 2); assert.equal(c.getSnapshot().cursor, null)
})
test('typed native client sends operations without credentials or paths', async () => {
  const calls = []
  const { libraryApi } = compile('library/client.ts', { './types': types, '@tauri-apps/api/core': { isTauri: () => true, invoke: async (command, args) => { calls.push([command, args]); return { ok: true, status: 201, data: document } } } })
  await libraryApi.upload(); await libraryApi.paste('Title', 'Notes')
  assert.deepEqual(calls[0], ['library_request', { operation: { kind: 'upload' } }])
  assert.deepEqual(calls[1][1], { operation: { kind: 'paste', title: 'Title', text: 'Notes' } })
})
test('native client maps unauthorized to the authentication gate and sanitizes errors', async () => {
  const { libraryApi } = compile('library/client.ts', { './types': types, '@tauri-apps/api/core': { isTauri: () => true, invoke: async () => ({ ok: false, status: 401, error: { code: 'raw-secret-internal' } }) } })
  await assert.rejects(libraryApi.upload(), e => e.code === 'sign_in_required' && !e.message.includes('raw-secret'))
})
test('runtime document guard rejects malformed and unsafe structure contracts', () => {
  assert.equal(types.parseDocument(document, true).id, document.id)
  for (const patch of [{ extraction_status: 'pretend' }, { extracted_text: 12 }, { extraction_structure: [{ kind: 'page', number: 1, start: 5, end: 3 }] }]) assert.throws(() => types.parseDocument({ ...document, ...patch }, true))
})
test('native library is unavailable in a browser and does not touch storage', async () => {
  const { libraryApi } = compile('library/client.ts', { './types': types, '@tauri-apps/api/core': { isTauri: () => false, invoke: () => { throw Error('must not run') } } })
  await assert.rejects(libraryApi.list(), e => e.code === 'desktop_required')
})
test('signed-in navigation offers library alongside the unchanged learning workspace', () => {
  const { Sidebar } = compile('components/Sidebar.tsx', { './Brand': { Brand: () => null } })
  const html = render(React.createElement(Sidebar, { libraryOpen: true, onNavigate: noop, onOpenSettings: noop }))
  assert.match(html, /Context Library/); assert.match(html, /Learning workspace/); assert.match(html, /aria-current="page"/)
})
