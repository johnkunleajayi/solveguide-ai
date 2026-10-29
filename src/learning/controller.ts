import type { LearningSession, PreparationInput, SessionApi } from './types'
export interface LearningState { phase:'loading'|'ready'|'busy'|'error'; draft:LearningSession|null; active:LearningSession|null; message:string|null; notice:string|null; ended:boolean }
export function createSessionController(api:SessionApi, denied:(error:unknown)=>void) {
 let state:LearningState={phase:'loading',draft:null,active:null,message:null,notice:null,ended:false}
 let generation=0,closed=false
 const listeners=new Set<()=>void>()
 const update=(patch:Partial<LearningState>)=>{state={...state,...patch};listeners.forEach(fn=>fn())}
 const failure=(error:unknown)=>{denied(error);update({phase:'error',message:error && typeof error==='object' && 'message' in error && typeof error.message==='string'?error.message:'Could not update session preparation. Refresh and try again.'})}
 async function change(action:()=>Promise<void>) { if(closed || state.phase==='busy') return false; const ticket=++generation; update({phase:'busy',message:null,notice:null}); try{await action(); if(closed || ticket!==generation) return false; update({phase:'ready'});return true}catch(error){if(!closed && ticket===generation)failure(error);return false} }
 return {
  activate(){closed=false},
  getSnapshot:()=>state,
  subscribe(fn:()=>void){listeners.add(fn);return()=>{listeners.delete(fn)}},
  async refresh(){if(closed || state.phase==='busy')return; const ticket=++generation;try{const value=await api.current();if(!closed && ticket===generation)update({...value,phase:'ready',message:null})}catch(error){if(!closed && ticket===generation)failure(error)}},
  save(input:PreparationInput,review=false){return change(async()=>{const draft=await api.save(input);if(closed)return;update({draft,notice:'Draft saved to your account.'});if(review){const ready=await api.ready(draft.id,draft.revision);if(!closed)update({draft:ready,notice:'Preparation reviewed and ready to start.'})}})},
  start(reviewed:{id:string;revision:number},replace:string|null){return change(async()=>{const draft=state.draft;if(!draft || draft.status!=='ready' || draft.id!==reviewed.id || draft.revision!==reviewed.revision)throw Error('Review the preparation first.');const active=await api.start(draft.id,draft.revision,replace);if(!closed)update({active,draft:null,ended:false})})},
  end(expected:{id:string;revision:number}){return change(async()=>{const active=state.active;if(!active || active.id!==expected.id || active.revision!==expected.revision)throw Error('The active session changed. Review it again.');await api.end(active.id,active.revision);if(!closed)update({active:null,ended:true})})},
  dispose(){closed=true;++generation;state={phase:'loading',draft:null,active:null,message:null,notice:null,ended:false};listeners.clear()},
 }
}
