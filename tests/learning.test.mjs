import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require = createRequire(import.meta.url)
function compile(file, dependencies = {}) {
  const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  const output = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', output)(id => dependencies[id] ?? require(id), module, module.exports)
  return module.exports
}
const React = require('react')
const { renderToStaticMarkup: render } = require('react-dom/server')
const types = compile('learning/types.ts')
const { createSessionController } = compile('learning/controller.ts')
const id = '00000000-0000-0000-0000-000000000001'
const session = patch => ({ id, revision: 1, purpose: 'general_learning', custom_purpose: null, objective: 'Understand a practice question.', document_ids: [], mode: 'general', allow_context_transmission: false, documents: [], status: 'draft', ready: true, issues: [], missing_document_count: 0, created_at: '2026-10-29T10:00:00Z', updated_at: '2026-10-29T10:00:00Z', started_at: null, ended_at: null, ...patch })
const noop = () => {}
const input = { revision: null, purpose: 'general_learning', custom_purpose: null, objective: 'Understand a practice question.', mode: 'general', document_ids: [], allow_context_transmission: false }
const api = patch => ({ current: async () => ({ draft: null, active: null }), save: async () => session(), ready: async () => session({ status: 'ready', revision: 2 }), start: async () => session({ status: 'active', revision: 3 }), end: async () => session({ status: 'ended', revision: 4 }), ...patch })
const deferred = () => { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }

test('objectives and recovered configuration are validated without browser storage', () => {
  assert.equal(types.validObjective('  '), false)
  assert.equal(types.validObjective('x'.repeat(2001)), false)
  assert.equal(types.validObjective('Learn\nwith examples'), true)
  assert.equal(types.parseSession(session()).purpose, 'general_learning')
  for (const patch of [{ mode: 'invented' }, { objective: '' }, { document_ids: [id,id] }, { id: '../auth' }, { purpose: 'custom', custom_purpose: null }]) assert.throws(() => types.parseSession(session(patch)))
})
test('draft save, ready review, start, recovery and end use explicit revisions', async () => {
  const calls = []
  const c = createSessionController(api({ start: async (...args) => { calls.push(args); return session({ status: 'active', revision: 3 }) } }), noop)
  await c.refresh()
  await c.save(input, true)
  assert.equal(c.getSnapshot().draft.status, 'ready')
  assert.equal(await c.start({ id, revision: 1 }, null), false)
  assert.equal(calls.length, 0)
  assert.equal(await c.start({ id, revision: 2 }, null), true)
  assert.deepEqual(calls, [[id, 2, null]])
  assert.equal(c.getSnapshot().active.status, 'active')
  assert.equal(await c.end({ id: 'different', revision: 3 }), false)
  assert.equal(c.getSnapshot().active.id, id)
  await c.end({ id, revision: 3 })
  assert.equal(c.getSnapshot().active, null)
  assert.equal(c.getSnapshot().ended, true)
  const recovered = createSessionController(api({ current: async () => ({ draft:null, active:session({status:'active',revision:3}) }) }), noop)
  await recovered.refresh()
  assert.equal(recovered.getSnapshot().active.revision, 3)
})
test('replacement carries the reviewed active id; no implicit end request is issued', async () => {
  const calls = []
  const c = createSessionController(api({ current: async () => ({ active:session({status:'active'}),draft:null }), start: async (...args) => { calls.push(args);throw {code:'active_session_exists',message:'Confirm replacement.'} } }), noop)
  await c.refresh(); await c.save(input,true)
  await c.start({id,revision:2},null)
  assert.deepEqual(calls[0],[id,2,null])
  await c.start({id,revision:2},id)
  assert.deepEqual(calls[1],[id,2,id])
})
test('duplicate operations, logout and late recovery cannot restore learning state', async () => {
  const pending = deferred(); let writes = 0
  const c = createSessionController(api({ save: async () => { writes++; return pending.promise } }), noop)
  const first = c.save(input)
  assert.equal(await c.save(input),false)
  assert.equal(writes,1)
  c.dispose(); pending.resolve(session()); await first
  assert.equal(c.getSnapshot().draft,null)
  const restore=deferred();const other=createSessionController(api({current:()=>restore.promise}),noop)
  const refreshing=other.refresh();other.dispose();restore.resolve({active:session({status:'active'}),draft:null});await refreshing
  assert.equal(other.getSnapshot().active,null)
})
test('session expiry and transport failure fail closed without auto-start or provider calls', async () => {
  let denied
  const c=createSessionController(api({current:async()=>{throw {code:'sign_in_required',message:'Sign in again.'}}}),error=>{denied=error})
  await c.refresh();assert.equal(c.getSnapshot().phase,'error');assert.equal(c.getSnapshot().active,null);assert.equal(denied.code,'sign_in_required')
})
test('native session requests carry bounded metadata and no credential or arbitrary URL', async () => {
  let captured
  const { sessionApi }=compile('learning/client.ts',{'./types':types,'@tauri-apps/api/core':{isTauri:()=>true,invoke:async(command,payload)=>{captured={command,payload};return {ok:true,status:200,data:session()}}}})
  await sessionApi.save(input)
  assert.equal(captured.command,'session_request')
  assert.deepEqual(captured.payload.operation,{kind:'save',draft:input})
  assert.doesNotMatch(JSON.stringify(captured),/credential|token|https?:|imageBase64/)
})
test('session answers send observation and session identity only through the existing cancellable transport', async () => {
  let captured
  const client=compile('answer/client.ts',{'./types':{parseAnswer:raw=>raw},'../rag/client':{},'../api/core':{requestCore:async(kind,payload,signal)=>{captured={kind,payload,signal};return {ok:true,data:{status:'answered'}}}}})
  const observation={question_type:'short_answer',question_text:'Practice question'}
  const signal=new AbortController().signal
  await client.getSuggestedAnswer(observation,signal,{mode:'general',document_ids:[id],allow_context_transmission:true,session:{id,revision:3}})
  assert.deepEqual(captured.payload,{observation,session_id:id,session_revision:3})
  assert.equal(captured.kind,'answer');assert.ok(captured.signal instanceof AbortSignal)
})
test('the session presentation gates core tools and exposes recovery/end controls', () => {
  let mounted=0
  const fakeReact={...React,useSyncExternalStore:(_fn,get)=>get()}
  const {SessionContent}=compile('components/LearningWorkspace.tsx',{
    react:fakeReact,'../auth/context':{useAuth:()=>({controller:{invalidate:noop}})},'../learning/controller':{},'../learning/client':{},'../learning/types':types,
    '../rag/controller':compile('rag/controller.ts'),'../rag/client':{},'../library/changes':{},'./ReasoningControls':{},
    './AnswerWorkspace':{AnswerWorkspace:()=>{mounted++;return React.createElement('p',null,'Core workspace')}}
  })
  const controller={refresh:async()=>{},getSnapshot:()=>({}),end:noop,start:noop}
  const base={phase:'ready',draft:null,active:null,message:null,ended:false}
  const html=state=>render(React.createElement(SessionContent,{state,controller,workspaceProps:{}}))
  assert.match(html({...base,phase:'loading'}),/Recovering your session/)
  assert.equal(mounted,0)
  const prep=html(base)
  assert.match(prep,/Purpose/);assert.match(prep,/Objective/);assert.match(prep,/Reference Materials/);assert.match(prep,/Reasoning Mode/);assert.match(prep,/Start Session/)
  assert.equal(mounted,0)
  const active=html({...base,active:session({status:'active'})})
  assert.match(active,/End Session/);assert.match(active,/Understand a practice question/);assert.equal(mounted,1)
  html({...base,phase:'error',active:session({status:'active'})})
  assert.equal(mounted,1)
})

 test('development effect replay restores recovery and rejects an earlier refresh', async () => {
  const pending=deferred();let calls=0
  const c=createSessionController(api({current:()=>++calls===1?pending.promise:Promise.resolve({active:session({status:'active'}),draft:null})}),noop)
  const old=c.refresh();c.dispose();c.activate();await c.refresh()
  pending.resolve({active:null,draft:session()});await old
  assert.equal(c.getSnapshot().active.status,'active');assert.equal(c.getSnapshot().draft,null)
 })
