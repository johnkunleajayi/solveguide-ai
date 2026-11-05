import type { MonitorSnapshot } from '../monitor/types'
import { AnswerRecommendationView } from './AnswerRecommendationView'
import type { QuestionObservation } from '../vision/types'
export function describeQuestion(observation:QuestionObservation|null) {
 const kind=observation?.question_type
 const visual=!!observation?.visual_task || kind==='visual_reasoning'
 const text=observation?.question_text??''
 const context=observation?.visible_context??[]
 const lines=[...text.split('\n'),...context.flatMap(value=>value.split('\n'))].map(line=>line.trim()).filter(Boolean)
 const ids=new Set([...text.matchAll(/^\s*(?:#{1,3}\s*)?(?:question|q)\s*(\d{1,3})\b(?!\s+of\s+\d)/gim)].map(match=>Number(match[1])))
 const count=ids.size>=2?ids.size:null
 const page=lines.map(line=>line.match(/\bquestion\s+(\d+)\s+of\s+(\d+)\b/i)).find(Boolean)
 const explicit=lines.map(line=>line.match(/^(?:page title|assessment title|challenge title|title|topic)\s*:\s*(.+)$/i)?.[1]).find(Boolean)
 const first=text.split('\n').find(line=>line.trim())?.trim().replace(/^#{1,3}\s*/,'')
 const observed=first && !/^(?:question|q)\s*\d+\b|^\d+[.)]\s/i.test(first)?first:null
 const fallback=kind==='code'?'Coding Challenge':visual?(count?'Visual Assessment':'Visual Question'):count?'Assessment':'Question'
 const raw=(explicit??observed??fallback).replace(/\s+/g,' ')
 const title=raw.length>100?raw.slice(0,97).replace(/\s+\S*$/,'')+'…':raw
 const type=visual?'Visual Assessment':kind==='code'?'Coding Challenge':kind==='multiple_choice'?'Multiple Choice':kind==='multiple_select'?'Multiple Select':kind==='mathematics'?'Mathematics':kind==='true_false'?'True / False':kind==='essay'?'Written Response':kind==='mixed'?'Mixed Assessment':'Question'
 return {title,description:count?`${type} · ${count} Questions`:page?`${type} · Question ${page[1]} of ${page[2]}`:type}
}
export function MonitorResult({snapshot,onOpenDocument}:{snapshot:MonitorSnapshot;onOpenDocument?:(id:string)=>void}) {
 const visual = snapshot.observation?.visual_task
 const identity=describeQuestion(snapshot.observation)
 const mode={general:'General',context_guided:'Context Guided',materials_only:'Materials Only'}[snapshot.mode]
 return <div className="monitor-result">
  <h2>{identity.title}</h2>
  <p className="eyebrow">{identity.description} · {mode}</p>
  {snapshot.observation?.question_text && <details open><summary>Observed question</summary><p className="monitor-question">{snapshot.observation.question_text}</p></details>}
  {visual && <section aria-label="Visual observation"><p>{visual.kind.replaceAll('_', ' ')} · {visual.image_count} images</p>
   {(!visual.complete || ((visual.kind === 'editing_prompt' || visual.requested_output === 'editing_prompt') && visual.direction !== 'established')) && <p role="status">Visual details or original-to-edited direction are unclear. Show the complete labelled task.</p>}
   {snapshot.observation?.warnings.length ? <ul aria-label="Visual uncertainty">{snapshot.observation.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul> : null}
   {visual.comparisons?.length ? <details><summary>Observed comparison facts</summary><ul>{visual.comparisons.map((row, i) => <li key={i}>{row.element} · {row.property} · {row.status}: {row.original} → {row.edited}</li>)}</ul></details> : null}
  </section>}
  {snapshot.answer && <AnswerRecommendationView state={{phase:'ready',result:snapshot.answer,error:null}} observation={snapshot.observation} onRequest={()=>{}} onCancel={()=>{}} enabled={false} headingId="monitor-recommendation-title" automatic onOpenDocument={onOpenDocument}/>}</div>
}
