import type { QuestionObservation } from '../vision/types'
import type { AnswerState } from '../answer/controller'
export function AnswerRecommendationView({ state, observation, onRequest, onCancel, enabled, onOpenDocument, automatic = false, headingId = 'recommendation-title' }: { headingId?: string; automatic?: boolean; state: AnswerState; observation: QuestionObservation | null; onRequest: () => void; onCancel: () => void; enabled: boolean; onOpenDocument?: (id: string) => void }) {
  const answer = state.result
  const abstained = answer?.status === 'insufficient_information' || answer?.status === 'unsupported'
  return <section className="recommendation-area" data-status={answer?.status ?? state.phase} aria-labelledby={headingId}>
    <header className="section-heading"><h2 id={headingId}><span className="section-index" aria-hidden="true">03</span>{answer?.question_type === 'essay' ? 'Suggested response' : 'Suggested answer'}</h2><span className="eyebrow">WHAT WE RECOMMEND</span></header>
    <div className="recommendation-content">
      {state.phase === 'idle' && <p>Ready when you are. Request a recommendation from the observed question.</p>}
      {state.phase === 'loading' && <div role="status" aria-live="polite"><span className="eyebrow">PREPARING A RECOMMENDATION</span><p>Considering the observed question. Your screenshot is not sent again.</p><button className="button" onClick={onCancel}>Cancel recommendation</button></div>}
      {state.error && <p role="alert" className="capture-error">{state.error.message}</p>}
      {answer && <>
        <p className="eyebrow" role="status">{answer.status === 'uncertain' ? 'TENTATIVE · REVIEW CAREFULLY' : answer.status === 'insufficient_information' ? 'MORE INFORMATION NEEDED' : answer.status === 'unsupported' ? 'UNSUPPORTED QUESTION' : 'SUGGESTED RESPONSE'}</p>
        {answer.selected_options.length > 0 && <ul className="recommended-options" aria-label="Recommended options">{answer.selected_options.map(label => <li key={label}><strong>{label}</strong><span>{observation?.options.find(option => option.label === label)?.text}</span></li>)}</ul>}
        {answer.true_false_answer !== null && <p className="answer-direct">{answer.true_false_answer ? 'True' : 'False'}</p>}
        {answer.answer_text && <p className="answer-direct">{answer.answer_text}</p>}
        {answer.code_answer && <pre className="answer-code" aria-label={`Suggested ${answer.code_answer.language ?? ''} code`}><code>{answer.code_answer.code}</code></pre>}
        <div className="recommendation-explanation"><h3>{abstained ? 'What to review' : answer.question_type === 'mathematics' ? 'Explanation / key steps' : 'Why'}</h3><p>{answer.explanation}</p>{answer.key_points.length > 0 && <ol>{answer.key_points.map((point, i) => <li key={i}>{point}</li>)}</ol>}</div>
        {!abstained && <p className="answer-confidence">Answer confidence · {Math.round(answer.confidence * 100)}%</p>}
        {answer.grounding && <section className="grounding-sources" aria-label="Evidence and sources"><h3>{answer.grounding.grounding_status === 'general_reasoning' ? 'General reasoning · not document-supported' : answer.grounding.grounding_status === 'insufficient_evidence' ? (answer.grounding.reasoning_mode === 'materials_only' ? 'Insufficient document evidence' : 'Insufficient information') : answer.grounding.grounding_status === 'mixed' ? 'Document evidence and general reasoning' : 'Document support'}</h3><p className="capture-privacy">{answer.grounding.reasoning_mode.replace('_', ' ')} · {answer.grounding.retrieval_method === 'lexical' ? 'Lexical retrieval' : answer.grounding.retrieval_method === 'semantic_pgvector' ? 'Semantic retrieval' : 'No retrieval performed'}. Citations identify document-supported parts only. Uncited reasoning is not document evidence; model-based support checks do not guarantee correctness.</p>{answer.grounding.citations.map(c => <details key={c.chunk_id}><summary>{c.document_title}{c.page_number !== null ? ` · Page ${c.page_number}` : ` · ${c.location}`}</summary><blockquote>{c.excerpt}</blockquote><p className="capture-privacy">Supports: {c.supports.join(', ')} · {c.location}</p>{onOpenDocument && <button className="button" onClick={() => onOpenDocument(c.document_id)}>Open source document</button>}</details>)}{answer.grounding.general_reasoning.length > 0 && <div><h4>General model reasoning · not document evidence</h4><ul>{answer.grounding.general_reasoning.map((point, i) => <li key={i}>{point}</li>)}</ul></div>}</section>}
        {answer.warnings.length > 0 && <section className="observation-warnings" aria-label="Answer warnings"><h4>Review notes</h4><ul>{answer.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></section>}
      </>}
      {!automatic && state.phase !== 'loading' && <button className="button button-primary" disabled={!enabled} onClick={onRequest}>{state.phase === 'idle' ? 'Get Suggested Answer' : 'Try Again'}</button>}
      <p className="capture-privacy">Each request sends the structured observation to the answer provider and may incur API charges. Grounded requests also send selected relevant passages after consent. Answer confidence is separate from reading confidence; both are estimates.</p>
    </div>
  </section>
}
