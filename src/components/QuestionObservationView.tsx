import type { ObservationState } from '../vision/controller'
export function QuestionObservationView({ state, onRetry, onCancel }: { state: ObservationState; onRetry: () => void; onCancel: () => void }) {
  const observation = state.observation
  if (state.phase === 'reading') return <div className="observation-content" role="status" aria-live="polite"><span className="eyebrow">READING VISUAL CONTENT</span><h3>Finding the question.</h3><p>Extracting visible content. No answer is being generated.</p><button className="button" onClick={onCancel}>Cancel reading</button></div>
  if (state.phase === 'error') return <div className="observation-content"><p role="alert">{state.error?.message}</p><button className="button" onClick={onRetry}>Retry reading</button></div>
  if (!observation) return <div className="answer-empty"><span className="answer-beam" aria-hidden="true" /><span className="eyebrow">FIRST, UNDERSTAND</span><h3>Bring the question<br />into focus.</h3><p>Capture a screen or window, then choose Read Question.<br />No answer will be generated.</p></div>
  const confidence = observation.extraction_confidence >= .85 ? 'High' : observation.extraction_confidence >= .6 ? 'Moderate' : 'Low'
  return <div className="observation-content">
    <div className="observation-summary" role="status"><span className="eyebrow">{observation.status === 'no_question' ? 'NO QUESTION DETECTED' : observation.status === 'unclear' ? 'QUESTION NEEDS REVIEW' : 'QUESTION DETECTED'}</span><span className="state-label">{observation.question_type.replaceAll('_', ' ')}</span></div>
    {observation.question_text ? <h3 className="observed-text">{observation.question_text}</h3> : <p>No readable question was found. Retake the capture or choose another source.</p>}
    {observation.instructions.length > 0 && <section aria-label="Visible instructions">{observation.instructions.map((instruction, i) => <p className="observed-text" key={i}>{instruction}</p>)}</section>}
    {observation.options.length > 0 && <ol className="observed-options" aria-label="Visible answer options">{observation.options.map(option => <li key={option.label}><span className="option-label">{option.label}</span><span className="observed-text">{option.text}</span></li>)}</ol>}
    <p className="observation-confidence">{confidence} extraction confidence · {Math.round(observation.extraction_confidence * 100)}%{observation.required_selection_count !== null && ` · Select ${observation.required_selection_count}`}</p>
    <p className="capture-privacy">Confidence estimates reading quality, not answer correctness. Review the capture for accuracy.</p>
    {observation.warnings.length > 0 && <section className="observation-warnings" aria-label="Extraction warnings"><h4>Review notes</h4><ul>{observation.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></section>}
    {observation.visible_context.length > 0 && <section aria-label="Visible supporting context"><h4>Visible context</h4>{observation.visible_context.map((context, i) => <p className="observed-text" key={i}>{context}</p>)}</section>}
    {observation.visual_elements.length > 0 && <section aria-label="Visible visual elements"><h4>Visual elements</h4>{observation.visual_elements.map((element, i) => <div className="observed-element" key={i}><span className="eyebrow">{element.kind}{element.language && ` · ${element.language}`}</span><p>{element.description}</p>{element.text && (element.kind === 'code' ? <pre><code>{element.text}</code></pre> : <p className="observed-text">{element.text}</p>)}</div>)}</section>}
  </div>
}
