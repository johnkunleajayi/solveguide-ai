import type { MonitorSnapshot } from '../monitor/types'
import { AnswerRecommendationView } from './AnswerRecommendationView'
export function MonitorResult({snapshot,onOpenDocument}:{snapshot:MonitorSnapshot;onOpenDocument?:(id:string)=>void}) {
 const visual = snapshot.observation?.visual_task
 return <div className="monitor-result">
  <p className="eyebrow">{snapshot.mode.replaceAll('_',' ')}{snapshot.questionNumber>0?` · Processing attempt ${snapshot.questionNumber} · Generation ${snapshot.generation}`:''}</p>
  {snapshot.observation?.question_text && <details open><summary>Observed question</summary><p className="monitor-question">{snapshot.observation.question_text}</p></details>}
  {visual && <section aria-label="Visual observation"><p>{visual.kind.replaceAll('_', ' ')} · {visual.image_count} images</p>
   {(!visual.complete || ((visual.kind === 'editing_prompt' || visual.requested_output === 'editing_prompt') && visual.direction !== 'established')) && <p role="status">Visual details or original-to-edited direction are unclear. Show the complete labelled task.</p>}
   {snapshot.observation?.warnings.length ? <ul aria-label="Visual uncertainty">{snapshot.observation.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul> : null}
   {visual.comparisons?.length ? <details><summary>Observed comparison facts</summary><ul>{visual.comparisons.map((row, i) => <li key={i}>{row.element} · {row.property} · {row.status}: {row.original} → {row.edited}</li>)}</ul></details> : null}
  </section>}
  {snapshot.answer && <AnswerRecommendationView state={{phase:'ready',result:snapshot.answer,error:null}} observation={snapshot.observation} onRequest={()=>{}} onCancel={()=>{}} enabled={false} headingId="monitor-recommendation-title" automatic onOpenDocument={onOpenDocument}/>}</div>
}
