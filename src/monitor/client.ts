import { invoke,isTauri } from '@tauri-apps/api/core'
import { parseMonitor,type MonitorApi } from './types'
export const monitorApi:MonitorApi=async operation=>{
 if(!isTauri())throw {code:'desktop_required',message:'Live Monitor requires SolveGuide for Windows.'}
 try{const raw=await invoke('monitor_control',{operation});const receivedAt=performance.now();const snapshot=parseMonitor(raw);if(snapshot.performance)snapshot.localPerformance={receivedAt,validationMs:performance.now()-receivedAt};return snapshot}catch(error){
 const code=typeof error==='string'?error:error && typeof error==='object' && 'code' in error?String(error.code):'monitor_unavailable'
 const multiMessage:Record<string,string>={answer_truncated:'The provider reached its output limit. Use fewer questions and solve again explicitly.',incomplete_assessment:'The response omitted a detected question. Use fewer questions and solve again explicitly.',capture_limit:'A collection holds at most 5 captures. Remove one before adding another.',image_too_large:'Combined captures exceed the image limit. Remove a capture or choose a smaller source.',multi_not_ready:'Add 2–5 captures and wait for capture to finish before solving.',multi_not_active:'Multi-Capture has ended.',not_monitoring:'Start or Resume monitoring before collecting captures.'}
 throw {code,message:multiMessage[code]??(code==='session_metadata_outdated'?'Restart the updated backend before grounded monitoring.':code==='session_changed'?'Recover a ready active session before monitoring.':code==='source_unavailable'?'The source is unavailable. Choose it again.':code==='already_monitoring'?'Pause or Stop the existing monitor first.':'Live Monitor is unavailable. Check the source, session and backend, then retry.')}
 }
}
