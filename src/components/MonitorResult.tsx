import type { MonitorSnapshot } from '../monitor/types'
import { AnswerRecommendationView } from './AnswerRecommendationView'
export function MonitorResult({snapshot,onOpenDocument}:{snapshot:MonitorSnapshot;onOpenDocument?:(id:string)=>void}) {
 return <div className="monitor-result"><p className="eyebrow">{snapshot.mode.replaceAll('_',' ')}{snapshot.questionNumber>0?` · Candidate ${snapshot.questionNumber} · Generation ${snapshot.generation}`:''}</p>{snapshot.observation?.question_text && <details open><summary>Observed question</summary><p className="monitor-question">{snapshot.observation.question_text}</p></details>}{snapshot.answer && <AnswerRecommendationView state={{phase:'ready',result:snapshot.answer,error:null}} observation={snapshot.observation} onRequest={()=>{}} onCancel={()=>{}} enabled={false} headingId="monitor-recommendation-title" automatic onOpenDocument={onOpenDocument}/>}</div>
}
