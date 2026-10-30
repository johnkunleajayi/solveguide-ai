import { initialMonitor,type MonitorApi,type MonitorOperation,type MonitorSnapshot } from './types'
export function createMonitorController(api:MonitorApi,denied:(error:unknown)=>void=()=>{}) {
 let state={snapshot:initialMonitor,busy:false,error:null as string|null};let generation=0;let closed=false;let polling=false
 const listeners=new Set<()=>void>()
 const update=(patch:Partial<typeof state>)=>{state={...state,...patch};listeners.forEach(fn=>fn())}
 const failed=(error:unknown)=>{denied(error);update({snapshot:{...state.snapshot,observation:null,answer:null},busy:false,error:error && typeof error==='object' && 'message' in error?String(error.message):'Could not update Live Monitor.'})}
 return {
 getSnapshot:()=>state,subscribe(fn:()=>void){listeners.add(fn);return()=>{listeners.delete(fn)}},activate(){closed=false},
 async refresh(){if(closed || polling || state.busy)return;polling=true;const ticket=generation;try{const snapshot=await api({kind:'snapshot'});if(!closed && ticket===generation)update({snapshot,error:null})}catch(error){if(!closed && ticket===generation)failed(error)}finally{polling=false}},
 async command(operation:MonitorOperation){if(closed || state.busy && operation.kind!=='stop' && operation.kind!=='pause')return false;const ticket=++generation;
 const clear=operation.kind==='stop'||operation.kind==='pause';update({busy:true,error:null,...(clear?{snapshot:{...state.snapshot,phase:operation.kind==='stop'?'stopped':'paused',observation:null,answer:null} as MonitorSnapshot}:{})});
 try{const snapshot=await api(operation);if(closed || ticket!==generation)return false;update({snapshot,busy:false});return true}catch(error){if(!closed && ticket===generation)failed(error);return false}},
 dispose(stop=false){closed=true;++generation;state={snapshot:initialMonitor,busy:false,error:null};listeners.clear();if(stop)void api({kind:'stop',reason:'workspace_disposed'}).catch(()=>{})},
 }
}
