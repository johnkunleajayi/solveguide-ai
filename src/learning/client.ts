import { invoke, isTauri } from '@tauri-apps/api/core'
import { parseSession, type PreparationState, type SessionApi } from './types'
const messages: Record<string,string> = { preparation_changed:'This preparation changed in another window. Refresh and review it again.', preparation_not_ready:'Review material readiness and consent before starting.', active_session_exists:'The active session changed. Refresh before confirming replacement.', session_changed:'This session is no longer active. Refresh to recover the current state.', preparation_not_found:'This preparation is no longer available.', document_not_found:'A selected document is no longer available. Review your materials.', database_schema:'Session storage needs the approved Alembic migration. Ask the operator to apply it.', database_unavailable:'Session storage is unavailable. Try again.', invalid_request:'Check your purpose, objective and selected materials.' }
async function request(operation: object): Promise<unknown> {
 if (!isTauri()) throw {code:'desktop_required',message:'Open SolveGuide desktop to prepare a session.'}
 try {
  const response = await invoke<{ok:boolean;status:number;data:unknown;error?:{code:string}}>('session_request',{operation})
  if (!response.ok) throw {code:response.status===401?'sign_in_required':response.error?.code ?? 'session_unavailable'}
  return response.data
 } catch(error) { const code = error && typeof error==='object' && 'code' in error && typeof error.code==='string'?error.code:'backend_unavailable'; throw {code,message:messages[code] ?? 'Could not update the session. Check the backend connection and retry.'} }
}
const required = (raw:unknown) => { const result=parseSession(raw); if(!result) throw Error('Missing preparation'); return result }
export const sessionApi:SessionApi={
 async current(){ const raw=await request({kind:'current'}) as PreparationState; if(!raw || typeof raw!=='object') throw Error('Invalid session state'); const draft=parseSession(raw.draft),active=parseSession(raw.active); if(draft && !['draft','ready'].includes(draft.status) || active && active.status!=='active') throw Error('Invalid lifecycle'); return {draft,active} },
 async save(draft){return required(await request({kind:'save',draft}))},
 async ready(id,revision){return required(await request({kind:'ready',id,revision}))},
 async start(id,revision,replace_active_id){return required(await request({kind:'start',preparation_id:id,revision,replace_active_id}))},
 async end(id,revision){return required(await request({kind:'end',id,revision}))},
}
