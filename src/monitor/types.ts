import { parseObservation, type QuestionObservation } from '../vision/types'
import { parseAnswer, type AnswerRecommendation } from '../answer/types'
import { parseGroundedAnswer } from '../rag/client'
import type { CaptureSource } from '../capture/types'
import type { ReasoningMode } from '../rag/types'
export const phases = ['stopped','monitoring','processing','answer_ready','paused','error'] as const
export interface MonitorSnapshot {
 phase:typeof phases[number];generation:number;questionNumber:number;source:CaptureSource|null;mode:ReasoningMode;documentIds:string[];
 observation:QuestionObservation|null;answer:AnswerRecommendation|null;message:string;panelVisible:boolean;privacyAvailable:boolean
}
export const initialMonitor:MonitorSnapshot={phase:'stopped',generation:0,questionNumber:0,source:null,mode:'general',documentIds:[],observation:null,answer:null,message:'Select a source and explicitly start monitoring.',panelVisible:false,privacyAvailable:true}
export function parseMonitor(raw:unknown):MonitorSnapshot {
 const value=raw as MonitorSnapshot
 const expected=['phase','generation','questionNumber','source','mode','documentIds','observation','answer','message','panelVisible','privacyAvailable']
 if(!value || typeof value!=='object' || Array.isArray(value) || Object.keys(value).length!==expected.length || !expected.every(key=>Object.hasOwn(value,key)) || !phases.includes(value.phase) || !Number.isSafeInteger(value.generation) || value.generation<0 || !Number.isInteger(value.questionNumber) || value.questionNumber<0 || value.questionNumber>60 || !['general','context_guided','materials_only'].includes(value.mode) || !Array.isArray(value.documentIds) || value.documentIds.length>5 || !value.documentIds.every(id=>typeof id==='string') || typeof value.message!=='string' || value.message.length>1000 || typeof value.panelVisible!=='boolean' || typeof value.privacyAvailable!=='boolean' || !(value.source===null || value.source && typeof value.source.title==='string' && typeof value.source.id==='string' && ['screen','window'].includes(value.source.kind))) throw Error('Invalid monitor status')
 const observation=value.observation===null?null:parseObservation(value.observation)
 if(value.answer!==null && !observation)throw Error('Answer without observation')
 const answer=value.answer===null?null:value.mode==='general'?parseAnswer(value.answer,observation!):parseGroundedAnswer(value.answer,observation!,{mode:value.mode,document_ids:value.documentIds,allow_context_transmission:true})
 if((value.phase==='stopped' || value.phase==='paused' || value.phase==='error') && (answer || observation))throw Error('Inactive monitor contained live content')
 return {...value,observation,answer}
}
export type MonitorOperation = {kind:'snapshot'|'pause'|'resume'|'show_panel'|'hide_panel'|'focus_panel'}|{kind:'stop';reason?:'user_requested'|'source_changed'|'workspace_disposed'}|{kind:'expand';expanded:boolean}|{kind:'start';source_id:string;source_kind:'screen'|'window';session_id:string;revision:number;config?:{intervalMs:number;stabilizeMs:number;requestIntervalSeconds:number;maxQuestions:number}}
export type MonitorApi=(operation:MonitorOperation)=>Promise<MonitorSnapshot>
