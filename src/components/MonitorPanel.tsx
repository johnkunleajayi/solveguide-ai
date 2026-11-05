import { useEffect,useState,useSyncExternalStore } from 'react'
import { createMonitorController } from '../monitor/controller'
import { monitorApi } from '../monitor/client'
import { useTheme,type Theme } from '../hooks/useTheme'
import { MultiCaptureControls } from './MultiCaptureControls'
import { MonitorResult } from './MonitorResult'
import { createReadyReporter } from '../monitor/performance'
export function MonitorPanel(){
 const {setTheme}=useTheme();const [expanded,setExpanded]=useState(false)
 const [controller]=useState(()=>createMonitorController(monitorApi));const state=useSyncExternalStore(controller.subscribe,controller.getSnapshot);const snapshot=state.snapshot
 const [reportReady]=useState(createReadyReporter)
 useEffect(()=>{const operation=reportReady(snapshot,performance.now());if(operation)void monitorApi(operation).catch(()=>{})},[snapshot,reportReady])
 useEffect(()=>{controller.activate();void controller.refresh();const timer=setInterval(()=>{void controller.refresh()},500);return()=>{clearInterval(timer);controller.dispose()}},[controller])
 useEffect(()=>{const listener=(event:StorageEvent)=>{if(event.key==='solveguide-theme' && ['dark','light','system'].includes(event.newValue??''))setTheme(event.newValue as Theme)};window.addEventListener('storage',listener);return()=>window.removeEventListener('storage',listener)},[setTheme])
 const running=['monitoring','processing','answer_ready'].includes(snapshot.phase)
 return <main className="monitor-panel" aria-labelledby="panel-title"><header><span className="eyebrow">SOLVEGUIDE AI · LIVE MONITOR</span><h1 id="panel-title">Learning, in view.</h1><div className="monitor-actions"><button className="button" onClick={()=>{void controller.command({kind:'hide_panel'})}}>Hide panel</button><button className="button" aria-expanded={expanded} onClick={()=>{void controller.command({kind:'expand',expanded:!expanded}).then(ok=>{if(ok)setExpanded(!expanded)})}}>{expanded?'Compact':'Expand'}</button></div></header><p role="status">{snapshot.phase.replaceAll('_',' ')} · {snapshot.message}</p><div className="monitor-actions">{running?<button className="button" onClick={()=>{void controller.command({kind:'pause'})}}>Pause</button>:snapshot.phase!=='stopped'?<button className="button" onClick={()=>{void controller.command({kind:'resume'})}}>Resume</button>:null}<button className="button" disabled={snapshot.phase==='stopped'} onClick={()=>{void controller.command({kind:'stop'})}}>Stop Monitoring</button></div>{state.error && <p role="alert" className="capture-error">{state.error}</p>}{!snapshot.privacyAvailable && <p role="alert">Capture protection is not verified for this panel.</p>}<MultiCaptureControls status={snapshot.multiCapture} enabled={running} busy={state.busy} onCommand={operation=>{void controller.command(operation)}}/>{!snapshot.multiCapture && <div className="monitor-actions"><button className="button" disabled={!snapshot.source} onClick={()=>{void controller.command({kind:'new_capture'})}}>New Capture</button><button className="button" disabled={!snapshot.answer && !running} onClick={()=>{void controller.command({kind:'dismiss'})}}>Dismiss</button></div>}<MonitorResult snapshot={snapshot}/><p className="capture-privacy">Automatic requests may incur API charges. Review suggestions critically. Live content is not saved.</p></main>
}
