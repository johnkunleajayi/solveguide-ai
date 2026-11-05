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
test('pause retains the solution; resume and source-change stop are explicit',async()=>{
 const pending=deferred(),calls=[];const c=createMonitorController(async op=>{calls.push(op);return op.kind==='pause'?pending.promise:op.kind==='stop'?{...active,phase:'stopped'}:active})
 await c.command(start);const pausing=c.command({kind:'pause'});assert.equal(c.getSnapshot().snapshot.answer,recommendation);assert.equal(c.getSnapshot().snapshot.phase,'paused')
 pending.resolve({...active,phase:'paused'});await pausing;assert.equal(c.getSnapshot().snapshot.answer,recommendation);await c.command({kind:'resume'});await c.command({kind:'stop'})
 assert.deepEqual(calls.map(v=>v.kind),['start','pause','resume','stop'])
})
test('logout/session unmount stops native work and ignores late answers',async()=>{
 const pending=deferred(),calls=[];const c=createMonitorController(op=>{calls.push(op.kind);return op.kind==='start'?pending.promise:Promise.resolve(initial)})
 const request=c.command(start);c.dispose(true);pending.resolve(active);await request
 assert.deepEqual(calls,['start','stop']);assert.equal(c.getSnapshot().snapshot.answer,null)
})
test('authentication errors stop monitoring without erasing the displayed solution',async()=>{
 let fail=false,denied;const c=createMonitorController(async()=>{if(fail)throw {code:'session_expired',message:'Sign in again.'};return active},e=>{denied=e})
 await c.refresh();fail=true;await c.refresh();assert.equal(c.getSnapshot().snapshot.answer,recommendation);assert.equal(denied.code,'session_expired');assert.match(c.getSnapshot().error,/Sign in/)
})
test('snapshot validation reuses strict contracts and permits retained inactive solutions',()=>{
 assert.equal(types.parseMonitor(active).answer.answer_text,recommendation.answer_text)
 for(const patch of [{answer:{...recommendation,selected_options:['FAKE']}},{observation:null},{generation:-1},{sessionToken:'must-not-cross-IPC'}])assert.throws(()=>types.parseMonitor({...active,...patch}))
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


test('floating monitor accepts Context Guided general-only attribution without accepting Materials Only bypasses',()=>{
 const raw={...recommendation,reasoning_mode:'context_guided',grounding_status:'general_reasoning',retrieval_method:'lexical',citations:[],general_reasoning:['General model knowledge, not document evidence.']}
 const parsed=types.parseMonitor({...active,mode:'context_guided',documentIds:['owned'],answer:raw})
 assert.equal(parsed.answer.grounding.grounding_status,'general_reasoning')
 assert.equal(parsed.answer.grounding.citations.length,0)
 assert.throws(()=>types.parseMonitor({...active,mode:'materials_only',documentIds:['owned'],answer:{...raw,reasoning_mode:'materials_only'}}))
})

test('DEBUG performance metadata is strict and cannot replace generation or expose local timestamps',()=>{
 const performance={traceId:'live-a-b-1',candidateId:'question-1-1',generation:1,observedToSnapshotMs:1234}
 assert.equal(types.parseMonitor({...active,performance}).performance.observedToSnapshotMs,1234)
 for(const invalid of [null,{}, {...performance,generation:2},{...performance,traceId:'private contents'}, {...performance,observedToSnapshotMs:-1},{...performance,secret:'hidden'}])assert.throws(()=>types.parseMonitor({...active,performance:invalid}))
 assert.throws(()=>types.parseMonitor({...active,performance,localPerformance:{receivedAt:1,validationMs:0}}))
 assert.throws(()=>types.parseMonitor({...initial,performance}))
})


test('New Capture and Dismiss erase immediately and reject late polls and commands',async()=>{
 for(const kind of ['new_capture','dismiss']) {
  const old=deferred(),action=deferred();let calls=0
  const c=createMonitorController(op=>op.kind===kind?action.promise:++calls===1?Promise.resolve(active):old.promise)
  await c.refresh();const poll=c.refresh();const command=c.command({kind})
  assert.equal(c.getSnapshot().snapshot.answer,null)
  assert.equal(c.getSnapshot().snapshot.observation,null)
  old.resolve(active);await poll;assert.equal(c.getSnapshot().snapshot.answer,null)
  action.resolve({...initial,phase:'monitoring',generation:2});await command
  assert.equal(c.getSnapshot().snapshot.answer,null)
 }
 const late=deferred();const c=createMonitorController(op=>op.kind==='start'?late.promise:Promise.resolve({...initial,phase:'monitoring'}))
 const starting=c.command(start);await c.command({kind:'dismiss'});late.resolve(active);assert.equal(await starting,false)
 assert.equal(c.getSnapshot().snapshot.answer,null)
})

test('transient snapshot transport failure retains the displayed answer',async()=>{
 let fail=false;const c=createMonitorController(async()=>{if(fail)throw Error('Network unavailable');return active})
 await c.refresh();fail=true;await c.refresh()
 assert.equal(c.getSnapshot().snapshot.answer,recommendation)
 assert.match(c.getSnapshot().error,/Network unavailable/)
})

test('floating panel exposes separate New Capture, Dismiss and Hide panel controls',()=>{
 const calls=[];const c=createMonitorController(async op=>{calls.push(op);return active})
 const hooks={...React,useEffect:noop,useState:fn=>[typeof fn==='function'?fn():fn,noop],useSyncExternalStore:()=>({snapshot:active,error:null})}
 const {MonitorPanel}=compile('components/MonitorPanel.tsx',{'react':hooks,'../monitor/controller':{createMonitorController:()=>c},'../monitor/client':{monitorApi:noop},'../hooks/useTheme':{useTheme:()=>({setTheme:noop})},'./MonitorResult':{MonitorResult:()=>null},'./MultiCaptureControls':compile('components/MultiCaptureControls.tsx'),'../monitor/performance':{createReadyReporter:()=>noop}})
 const html=render(React.createElement(MonitorPanel));assert.match(html,/>New Capture</);assert.match(html,/>Dismiss</);assert.match(html,/>Hide panel</)
 assert.equal(calls.length,0)
})


test('timeouts, Pause, Stop and capture failures preserve the solution and separate status',async()=>{
 for(const phase of ['paused','stopped','error']) {
  const retained={...active,phase,message:'Monitoring timed out or stopped.'}
  assert.equal(types.parseMonitor(retained).answer.answer_text,recommendation.answer_text)
  let current=active;const c=createMonitorController(async()=>current)
  await c.refresh();current=retained;await c.refresh()
  assert.equal(c.getSnapshot().snapshot.answer,recommendation)
  assert.equal(c.getSnapshot().snapshot.message,retained.message)
  for(const kind of ['pause','stop']) {
   await c.command({kind});assert.equal(c.getSnapshot().snapshot.answer,recommendation)
  }
  const view=compile('components/AnswerRecommendationView.tsx')
  const {MonitorResult}=compile('components/MonitorResult.tsx',{'./AnswerRecommendationView':view})
  assert.match(render(React.createElement(MonitorResult,{snapshot:retained})),/A learning example/)
 }
})

test('Dismiss and New Capture can clear retained stopped solutions and reject old polls',async()=>{
 for(const kind of ['dismiss','new_capture']) {
  const old=deferred(),action=deferred();let count=0
  const retained={...active,phase:'stopped'}
  const c=createMonitorController(op=>op.kind===kind?action.promise:++count===1?Promise.resolve(retained):old.promise)
  await c.refresh();const poll=c.refresh();const clearing=c.command({kind})
  assert.equal(c.getSnapshot().snapshot.answer,null)
  old.resolve(retained);await poll;assert.equal(c.getSnapshot().snapshot.answer,null)
  action.resolve({...initial,phase:kind==='dismiss'?'stopped':'monitoring'});await clearing
  assert.equal(c.getSnapshot().snapshot.answer,null)
 }
})


test('multi-capture controls enforce 2-5 captures and expose ordered removal',()=>{
 const {MultiCaptureControls}=compile('components/MultiCaptureControls.tsx')
 const calls=[];const props={enabled:true,busy:false,onCommand:op=>calls.push(op)}
 const buttons=node=>{if(!node || typeof node!=='object')return [];return [...(node.type==='button'?[node]:[]),...React.Children.toArray(node.props?.children).flatMap(buttons)]}
 const start=MultiCaptureControls({...props,status:null});start.props.onClick();assert.equal(calls[0].kind,'multi_start')
 const collecting=MultiCaptureControls({...props,status:{count:2,adding:false,solving:false}})
 const html=render(collecting);assert.match(html,/2 \/ 5 captures/);assert.match(html,/Automatic detection is suspended/)
 const controls=buttons(collecting)
 controls.find(b=>b.props['aria-label']==='Remove capture 2').props.onClick()
 controls.find(b=>b.props.children==='Add Capture').props.onClick()
 controls.find(b=>b.props.children==='Solve').props.onClick()
 controls.find(b=>b.props.children==='Cancel').props.onClick()
 assert.deepEqual(calls.slice(1),[{kind:'multi_remove',index:1},{kind:'multi_add'},{kind:'multi_solve'},{kind:'multi_cancel'}])
 for(const count of [0,1])assert.equal(buttons(MultiCaptureControls({...props,status:{count,adding:false,solving:false}})).find(b=>b.props.children==='Solve').props.disabled,true)
 assert.equal(buttons(MultiCaptureControls({...props,status:{count:5,adding:false,solving:false}})).find(b=>b.props.children==='Add Capture').props.disabled,true)
 const solving=buttons(MultiCaptureControls({...props,busy:true,status:{count:2,adding:false,solving:true}}))
 assert.equal(solving.find(b=>b.props.children==='Cancel').props.disabled,undefined)
})

test('multi-capture status cannot expose images or exceed native bounds',()=>{
 assert.equal(types.parseMonitor({...initial,multiCapture:{count:2,adding:false,solving:true}}).multiCapture.count,2)
 for(const multiCapture of [{count:6,adding:false,solving:false},{count:1,adding:false,solving:true},{count:2,adding:false,solving:false,images:['private']}])assert.throws(()=>types.parseMonitor({...initial,multiCapture}))
})

test('Cancel, Pause and Stop supersede a pending multi-capture solve',async()=>{
 for(const kind of ['multi_cancel','pause','stop']) {
  const late=deferred();const c=createMonitorController(op=>op.kind==='multi_solve'?late.promise:Promise.resolve(initial))
  const solving=c.command({kind:'multi_solve'});assert.equal(c.getSnapshot().snapshot.answer,null)
  await c.command({kind});late.resolve(active);assert.equal(await solving,false)
  assert.equal(c.getSnapshot().snapshot.answer,null);assert.equal(c.getSnapshot().snapshot.multiCapture,null)
 }
})


test('question identity uses observed titles and never exposes run identifiers',()=>{
 const view=compile('components/AnswerRecommendationView.tsx')
 const {MonitorResult,describeQuestion}=compile('components/MonitorResult.tsx',{'./AnswerRecommendationView':view})
 const obs={...observation,question_type:'visual_reasoning',question_text:'Corporate Presentation Redesign Challenge\n'+Array.from({length:5},(_,i)=>`Question ${i+1}: Describe the visible change.`).join('\n')}
 const identity=describeQuestion(obs)
 assert.equal(identity.title,'Corporate Presentation Redesign Challenge')
 assert.equal(identity.description,'Visual Assessment · 5 Questions')
 const html=render(React.createElement(MonitorResult,{snapshot:{...active,observation:obs,answer:null,generation:73014444035}}))
 assert.match(html,/Corporate Presentation Redesign Challenge/)
 assert.doesNotMatch(html,/Processing attempt|Generation|73014444035/)
 assert.equal(describeQuestion({...observation,question_type:'code',question_text:'',visible_context:['Title: Python Coding Challenge — Longest Unique Substring']}).title,'Python Coding Challenge — Longest Unique Substring')
 assert.equal(describeQuestion({...observation,question_type:'visual_reasoning',question_text:null}).title,'Visual Question')
 assert.equal(describeQuestion({...observation,question_type:'code',question_text:null}).title,'Coding Challenge')
 assert.equal(describeQuestion({...obs,question_text:'Question 1: New assessment',visible_context:['Page title: Executive Dashboard Analysis']}).title,'Executive Dashboard Analysis')
})
