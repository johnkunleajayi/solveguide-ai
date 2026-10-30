import { invoke,isTauri } from '@tauri-apps/api/core'
import { parseMonitor,type MonitorApi } from './types'
export const monitorApi:MonitorApi=async operation=>{
 if(!isTauri())throw {code:'desktop_required',message:'Live Monitor requires SolveGuide for Windows.'}
 try{return parseMonitor(await invoke('monitor_control',{operation}))}catch(error){
 const code=typeof error==='string'?error:error && typeof error==='object' && 'code' in error?String(error.code):'monitor_unavailable'
 throw {code,message:code==='session_metadata_outdated'?'Restart the updated backend before grounded monitoring.':code==='session_changed'?'Recover a ready active session before monitoring.':code==='source_unavailable'?'The source is unavailable. Choose it again.':code==='already_monitoring'?'Pause or Stop the existing monitor first.':'Live Monitor is unavailable. Check the source, session and backend, then retry.'}
 }
}
