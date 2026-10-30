import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
const require=createRequire(import.meta.url)
const React=require('react')
const {renderToStaticMarkup:render}=require('react-dom/server')
function compile(file,deps={}) {
 const source=readFileSync(new URL(`../src/${file}`,import.meta.url),'utf8')
 const output=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText
 const module={exports:{}};new Function('require','module','exports',output)(id=>deps[id]??require(id),module,module.exports);return module.exports
}
const vision=compile('vision/types.ts'),answer=compile('answer/types.ts')
const rag=compile('rag/client.ts',{'../library/client':{},'../answer/types':answer})
const types=compile('monitor/types.ts',{'../vision/types':vision,'../answer/types':answer,'../rag/client':rag})
const {createMonitorController}=compile('monitor/controller.ts',{'./types':types})
const initial=types.initialMonitor
const noop=()=>{}
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r});return {resolve,promise}}
const observation={status:'detected',question_type:'short_answer',question_text:'Practice question?',options:[],instructions:[],required_selection_count:null,visible_context:[],visual_elements:[],extraction_confidence:0.9,warnings:[]}
const recommendation={status:'answered',question_type:'short_answer',answer_text:'A learning example.',selected_options:[],true_false_answer:null,code_answer:null,explanation:'A concise educational explanation.',key_points:[],confidence:0.8,warnings:[]}
const active={...initial,phase:'answer_ready',questionNumber:1,generation:1,observation,answer:recommendation}
const start={kind:'start',source_id:'opaque-native-id',source_kind:'window',session_id:'00000000-0000-0000-0000-000000000001',revision:3}

test('monitor controller never starts on startup/recovery and polls with backpressure',async()=>{
 const calls=[];const pending=deferred();const c=createMonitorController(op=>{calls.push(op);return pending.promise})
 assert.equal(c.getSnapshot().snapshot.phase,'stopped');assert.equal(calls.length,0)
 const first=c.refresh();await c.refresh();assert.deepEqual(calls,[{kind:'snapshot'}]);pending.resolve(initial);await first
 assert.equal(c.getSnapshot().snapshot.phase,'stopped')
})
test('stop wins over pending startup and stale snapshot responses',async()=>{
 const pending=deferred();const c=createMonitorController(op=>op.kind==='start'?pending.promise:Promise.resolve(initial))
 const starting=c.command(start);await c.command({kind:'stop'});pending.resolve(active);assert.equal(await starting,false);assert.equal(c.getSnapshot().snapshot.answer,null)
 const old=deferred();const d=createMonitorController(op=>op.kind==='snapshot'?old.promise:Promise.resolve(initial));const refresh=d.refresh();await d.command({kind:'stop'});old.resolve(active);await refresh;assert.equal(d.getSnapshot().snapshot.phase,'stopped')
})
test('pause clears obsolete answers synchronously; resume and source-change stop are explicit',async()=>{
 const pending=deferred(),calls=[];const c=createMonitorController(async op=>{calls.push(op);return op.kind==='pause'?pending.promise:op.kind==='stop'?initial:active})
 await c.command(start);const pausing=c.command({kind:'pause'});assert.equal(c.getSnapshot().snapshot.answer,null);assert.equal(c.getSnapshot().snapshot.phase,'paused')
 pending.resolve({...initial,phase:'paused'});await pausing;await c.command({kind:'resume'});await c.command({kind:'stop'})
 assert.deepEqual(calls.map(v=>v.kind),['start','pause','resume','stop'])
})
test('logout/session unmount stops native work and ignores late answers',async()=>{
 const pending=deferred(),calls=[];const c=createMonitorController(op=>{calls.push(op.kind);return op.kind==='start'?pending.promise:Promise.resolve(initial)})
 const request=c.command(start);c.dispose(true);pending.resolve(active);await request
 assert.deepEqual(calls,['start','stop']);assert.equal(c.getSnapshot().snapshot.answer,null)
})
test('provider/transport errors clear old content and propagate auth expiry',async()=>{
 let fail=false,denied;const c=createMonitorController(async()=>{if(fail)throw {code:'session_expired',message:'Sign in again.'};return active},e=>{denied=e})
 await c.refresh();fail=true;await c.refresh();assert.equal(c.getSnapshot().snapshot.answer,null);assert.equal(denied.code,'session_expired');assert.match(c.getSnapshot().error,/Sign in/)
})
test('snapshot validation reuses strict observation/answer contracts and rejects inactive content',()=>{
 assert.equal(types.parseMonitor(active).answer.answer_text,recommendation.answer_text)
 for(const patch of [{phase:'stopped'},{phase:'paused'},{answer:{...recommendation,selected_options:['FAKE']}},{observation:null},{generation:-1},{sessionToken:'must-not-cross-IPC'}])assert.throws(()=>types.parseMonitor({...active,...patch}))
})
test('Materials Only citations remain selected-document scoped in the monitor',()=>{
 const raw={...recommendation,reasoning_mode:'materials_only',grounding_status:'document_supported',retrieval_method:'lexical',general_reasoning:[],citations:[{chunk_id:'00000000-0000-0000-0000-000000000001',document_id:'owned',document_title:'Practice reference',page_number:1,location:'Page 1',excerpt:'Supporting passage.',supports:['answer','explanation']}]}
 assert.equal(types.parseMonitor({...active,mode:'materials_only',documentIds:['owned'],answer:raw}).answer.grounding.citations.length,1)
 assert.throws(()=>types.parseMonitor({...active,mode:'materials_only',documentIds:['other'],answer:raw}))
})
test('native monitor IPC carries only typed controls; no credentials or image transport in React',async()=>{
 const calls=[];const {monitorApi}=compile('monitor/client.ts',{'./types':types,'@tauri-apps/api/core':{isTauri:()=>true,invoke:async(...args)=>{calls.push(args);return initial}}})
 await monitorApi(start);await monitorApi({kind:'hide_panel'});await monitorApi({kind:'show_panel'})
 assert.equal(calls[0][0],'monitor_control');assert.deepEqual(calls[0][1],{operation:start});assert.doesNotMatch(JSON.stringify(calls),/image_base64|bearer|credential|https?:/)
})
test('Live Monitor exposes activation consent, source selection and immediate stop during startup',()=>{
 const fakeReact={...React,useSyncExternalStore:()=>({snapshot:initial,busy:true,error:null})}
 const {LiveMonitor}=compile('components/LiveMonitor.tsx',{react:fakeReact,'../auth/context':{useAuth:()=>({controller:{invalidate:noop}})},'../capture/native':{},'../monitor/controller':{createMonitorController:()=>({})},'../monitor/client':{},'./MonitorResult':{MonitorResult:()=>null}})
 const html=render(React.createElement(LiveMonitor,{session:{id:'session',revision:1,ready:true}}))
 assert.match(html,/Start Monitoring/);assert.match(html,/Stop Monitoring/);assert.match(html,/I authorize automatic AI requests/);assert.match(html,/Choose explicitly/);assert.match(html,/at most 2 candidates/)
})
test('automatic results display citations and abstention without a fake retry action',()=>{
 const view=compile('components/AnswerRecommendationView.tsx')
 const {MonitorResult}=compile('components/MonitorResult.tsx',{'./AnswerRecommendationView':view})
 const html=render(React.createElement(MonitorResult,{snapshot:active}));assert.match(html,/A learning example/);assert.doesNotMatch(html,/Try Again|Get Suggested Answer/)
 const abstain=render(React.createElement(MonitorResult,{snapshot:{...active,answer:{...recommendation,status:'insufficient_information',answer_text:null,confidence:0,warnings:['More evidence needed.']}}}));assert.match(abstain,/MORE INFORMATION NEEDED/)
})
test('panel lifecycle polling cannot start a monitor and dismissal does not stop it',async()=>{
 const calls=[];const c=createMonitorController(async op=>{calls.push(op.kind);return initial});await c.refresh();await c.command({kind:'expand',expanded:true});await c.command({kind:'hide_panel'});c.dispose();assert.deepEqual(calls,['snapshot','expand','hide_panel'])
})
