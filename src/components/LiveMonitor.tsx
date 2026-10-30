import { useEffect,useState,useSyncExternalStore } from 'react'
import { useAuth } from '../auth/context'
import { nativeCapture } from '../capture/native'
import type { CaptureSource } from '../capture/types'
import type { LearningSession } from '../learning/types'
import { createMonitorController } from '../monitor/controller'
import { monitorApi } from '../monitor/client'
import { MonitorResult } from './MonitorResult'
export function LiveMonitor({session,onOpenDocument,onRunningChange}:{session:LearningSession;onOpenDocument?:(id:string)=>void;onRunningChange?:(running:boolean)=>void}) {
 const {controller:auth}=useAuth()
 const [controller]=useState(()=>createMonitorController(monitorApi,auth.invalidate))
 const state=useSyncExternalStore(controller.subscribe,controller.getSnapshot)
 const [sources,setSources]=useState<CaptureSource[]>([]);const [selected,setSelected]=useState('');const [consent,setConsent]=useState(false);const [sourceError,setSourceError]=useState<string|null>(null);const [listing,setListing]=useState(false)
 const snapshot=state.snapshot;const running=['monitoring','processing','answer_ready'].includes(snapshot.phase)
 useEffect(()=>{controller.activate();void controller.refresh();const timer=setInterval(()=>{void controller.refresh()},700);return()=>{clearInterval(timer);controller.dispose(true)}},[controller])
 useEffect(()=>{onRunningChange?.(running);return()=>onRunningChange?.(false)},[running,onRunningChange])
 const discover=async()=>{setListing(true);setSourceError(null);try{setSources((await nativeCapture.listSources()).filter(s=>s.kind!=='region'))}catch{setSourceError('Could not list sources. Restore the application and retry.')}finally{setListing(false)}}
 const source=sources.find(s=>s.id===selected)
 return <section className="live-monitor" aria-labelledby="live-monitor-title">
 <header><div><span className="eyebrow"><span className="signal-dot" aria-hidden="true"/>LIVE QUESTION MONITOR</span><h1 id="live-monitor-title">Stay with the question.</h1><p>Explicitly monitor one source for authorized learning and practice. Stable new questions are read and answered automatically.</p></div><span className="state-label" role="status">{state.busy && snapshot.phase==='stopped'?'Starting / updating':snapshot.phase.replaceAll('_',' ')}</span></header>
 {(snapshot.phase!=='stopped' || state.busy) && <div className="monitor-actions monitor-toolbar">{running || state.busy?<button className="button" onClick={()=>{void controller.command({kind:'pause'})}}>Pause</button>:<button className="button" disabled={state.busy || !consent} onClick={()=>{void controller.command({kind:'resume'})}}>Resume</button>}<button className="button" onClick={()=>{void controller.command({kind:'stop'})}}>Stop Monitoring</button><button className="button" disabled={state.busy} onClick={()=>{void controller.command({kind:'show_panel'})}}>Reopen answer panel</button><button className="button" disabled={state.busy} onClick={()=>{void controller.command({kind:'focus_panel'})}}>Focus panel for keyboard use</button></div>}
 {!running && <div className="monitor-setup"><button className="button" disabled={listing || state.busy} onClick={()=>{void discover()}}>{listing?'Finding sources…':'Choose / refresh sources'}</button><label>Window or monitor<select value={selected} disabled={state.busy} onChange={e=>{setSelected(e.target.value);void controller.command({kind:'stop',reason:'source_changed'})}}><option value="">Choose explicitly</option>{sources.map(s=><option key={s.id} value={s.id}>{s.kind==='window'?'Window':'Screen'} · {s.title}</option>)}</select></label><label className="monitor-consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I authorize automatic AI requests for this source. Stable candidate images go to OpenAI; observations and learning intent go to the answer provider. Grounded modes send consented selected passages. API charges apply: at most 2 candidates/minute and 60 candidates per activation. Materials Only may add a verification call.</span></label><button className="button button-primary" disabled={!source || !consent || !session.ready || state.busy} onClick={()=>{if(source && source.kind!=='region')void controller.command({kind:'start',source_id:source.id,source_kind:source.kind,session_id:session.id,revision:session.revision})}}>Start Monitoring</button></div>}
 <p role="status" className="monitor-status">{snapshot.source?.title && <strong>{snapshot.source.title} · </strong>}{snapshot.message}</p>
 {(state.error || sourceError) && <p className="capture-error" role="alert">{state.error ?? sourceError}</p>}
 {!snapshot.privacyAvailable && <p className="capture-error" role="alert">Capture protection could not be verified for the answer panel. Check Screen-share privacy in Settings.</p>}
 <MonitorResult snapshot={snapshot} onOpenDocument={onOpenDocument}/>
 </section>
}
