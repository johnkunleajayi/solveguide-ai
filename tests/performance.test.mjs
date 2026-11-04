import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import ts from 'typescript'
const require=createRequire(import.meta.url)
function compile(file,deps={}) {
 const output=ts.transpileModule(readFileSync(new URL(`../src/${file}`,import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText
 const module={exports:{}};new Function('require','module','exports',output)(id=>deps[id]??require(id),module,module.exports);return module.exports
}
const {createReadyReporter}=compile('monitor/performance.ts')
const ready={phase:'answer_ready',generation:4294967297,answer:{answer_text:'private'},performance:{traceId:'live-a-b-1',candidateId:'question-1-1',generation:4294967297,observedToSnapshotMs:1000},localPerformance:{receivedAt:100,validationMs:2}}
test('UI-ready uses a local monotonic interval and emits no learning content',()=>{
 const report=createReadyReporter();const operation=report(ready,135)
 assert.deepEqual(operation,{kind:'performance_ready',generation:4294967297,receipt_to_ready_ms:35,validation_ms:2})
 assert.doesNotMatch(JSON.stringify(operation),/private|answer_text|traceId|credential/)
 assert.equal(report(ready,140),null)
})
test('missing/backwards/nonfinite clocks and inactive content never become zero-latency successes',()=>{
 for(const snapshot of [{...ready,localPerformance:undefined},{...ready,performance:undefined},{...ready,answer:null},{...ready,phase:'paused'}])assert.equal(createReadyReporter()(snapshot,135),null)
 for(const now of [99,Infinity,NaN,300101])assert.equal(createReadyReporter()(ready,now),null)
 assert.equal(createReadyReporter()({...ready,localPerformance:{receivedAt:100,validationMs:NaN}},135),null)
})
test('a fresh generation can report once without reusing obsolete timing',()=>{
 const report=createReadyReporter();assert.ok(report(ready,135))
 const next={...ready,generation:4294967298,performance:{...ready.performance,generation:4294967298,candidateId:'question-1-2'},localPerformance:{receivedAt:200,validationMs:3}}
 assert.equal(report(next,230).receipt_to_ready_ms,30)
 assert.equal(report({...next,phase:'stopped',answer:null},250),null)
})
test('normal IPC snapshots do not create diagnostic traffic; enabled snapshots add local timing',async()=>{
 const calls=[];const fakeTypes={parseMonitor:raw=>raw}
 const raw={phase:'stopped',answer:null}
 const {monitorApi}=compile('monitor/client.ts',{'./types':fakeTypes,'@tauri-apps/api/core':{isTauri:()=>true,invoke:async(...args)=>{calls.push(args);return raw}}})
 assert.equal((await monitorApi({kind:'snapshot'})).localPerformance,undefined)
 assert.equal(calls.length,1)
 raw.performance=ready.performance
 assert.ok((await monitorApi({kind:'snapshot'})).localPerformance.receivedAt>=0)
})
