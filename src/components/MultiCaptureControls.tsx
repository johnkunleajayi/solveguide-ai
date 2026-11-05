import type { MonitorOperation, MultiCaptureStatus } from '../monitor/types'
export function MultiCaptureControls({status,enabled,busy,onCommand}:{status:MultiCaptureStatus|null;enabled:boolean;busy:boolean;onCommand:(operation:MonitorOperation)=>void}) {
 if(!status)return <button className="button" disabled={!enabled || busy} onClick={()=>onCommand({kind:'multi_start'})}>Multi-Capture</button>
 return <section aria-label="Multi-Capture" className="monitor-result">
  <p role="status">{status.solving?'Solving collected captures…':status.adding?'Adding capture…':`Multi-Capture · ${status.count} / 5 captures`}</p>
  <p>Collect 2–5 views of one question in reading order. Automatic detection is suspended. Only Solve sends them to AI.</p>
  {!status.solving && status.count>0 && <ol aria-label="Collected captures">{Array.from({length:status.count},(_,index)=><li key={index}>Capture {index+1} <button className="button" disabled={busy || status.adding} aria-label={`Remove capture ${index+1}`} onClick={()=>onCommand({kind:'multi_remove',index})}>Remove</button></li>)}</ol>}
  <div className="monitor-actions">
   <button className="button" disabled={busy || status.adding || status.solving || status.count>=5} onClick={()=>onCommand({kind:'multi_add'})}>Add Capture</button>
   <button className="button button-primary" disabled={busy || status.adding || status.solving || status.count<2} onClick={()=>onCommand({kind:'multi_solve'})}>Solve</button>
   <button className="button" onClick={()=>onCommand({kind:'multi_cancel'})}>Cancel</button>
  </div>
 </section>
}
