import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useAuth } from '../auth/context'
import { createSessionController, type LearningState } from '../learning/controller'
import { sessionApi } from '../learning/client'
import { purposes, purposeDescriptions, purposeMap, purposeLabel, objectiveFor, validPreparationObjective, type Purpose, type PreparationInput } from '../learning/types'
import { createReasoningController } from '../rag/controller'
import { ragApi } from '../rag/client'
import { subscribeLibraryChanges } from '../library/changes'
import { ReasoningControls } from './ReasoningControls'
import { AnswerWorkspace } from './AnswerWorkspace'

type Controller = ReturnType<typeof createSessionController>
type WorkspaceProps = Parameters<typeof AnswerWorkspace>[0]
const steps = ['Purpose', 'Objective', 'Reference Materials', 'Reasoning Mode', 'Review']

export function LearningWorkspace(props: WorkspaceProps) {
  const { controller: auth } = useAuth()
  const [controller] = useState(() => createSessionController(sessionApi, auth.invalidate))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => {
    controller.activate()
    void controller.refresh()
    const refresh = () => { if (document.visibilityState === 'visible') void controller.refresh() }
    window.addEventListener('focus', refresh)
    const timer = setInterval(refresh, 60_000)
    const stopLibrary = subscribeLibraryChanges(refresh)
    return () => { clearInterval(timer); window.removeEventListener('focus', refresh); stopLibrary(); controller.dispose() }
  }, [controller])
  return <SessionContent state={state} controller={controller} workspaceProps={props} />
}

export function SessionContent({ state, controller, workspaceProps }: { state: LearningState; controller: Controller; workspaceProps: WorkspaceProps }) {
  const [preparing, setPreparing] = useState(false)
  const [reload, setReload] = useState(0)
  const [ending, setEnding] = useState<{ id: string; revision: number } | null>(null)
  const active = state.active
  if (state.phase === 'loading') return <section className="session-loading" role="status">Recovering your session preparation…</section>
  if (active && !preparing) return <>
    <section className="session-summary" aria-labelledby="session-title">
      <div><span className="eyebrow">ACTIVE LEARNING SESSION</span><h2 id="session-title">{purposeLabel(active.purpose)}</h2><p className="session-objective">{active.objective}</p><p className="session-metadata">{active.mode.replaceAll('_', ' ')} · {active.documents.length} references · {active.mode === 'general' ? 'No document retrieval' : 'Selected passage transmission consented'}</p></div>
      <div className="library-actions"><button className="button" disabled={state.phase === 'busy'} onClick={() => setPreparing(true)}>Prepare another session</button><button className="button" disabled={state.phase === 'busy'} onClick={() => setEnding({ id: active.id, revision: active.revision })}>End Session</button><button className="button" disabled={state.phase === 'busy'} onClick={() => { void controller.refresh() }}>Refresh session</button></div>
      {ending && <div className="session-confirm" role="group" aria-label="End session confirmation"><p>End the reviewed session and clear this window’s ephemeral capture, question and answer?</p><button className="button" onClick={() => setEnding(null)}>Keep session</button><button className="button" disabled={state.phase === 'busy'} onClick={() => { void controller.end(ending).then(ok => { if (ok) setEnding(null) }) }}>End and clear workspace</button></div>}
    </section>
    {state.message && <p className="capture-error" role="alert">{state.message}</p>}
    {active.issues.map(issue => <p className="capture-error" role="status" key={issue}>{issue}</p>)}
    {state.phase === 'ready' ? <AnswerWorkspace key={`${active.id}:${active.revision}:${active.ready}:${active.document_ids.join(',')}:${active.documents.map(d=>d.index_generation??'').join(',')}`} {...workspaceProps} preparation={active} /> : <p role="status">Session access is paused until its state can be confirmed.</p>}
  </>
  return <>
    {state.ended && <p className="analysis-notice" role="status">Session ended. Live question and answer content was not saved.</p>}
    {active && <button className="button" onClick={() => setPreparing(false)}>Return to active session</button>}
    <PreparationForm key={reload} state={state} controller={controller} onStarted={() => setPreparing(false)} />
    <button className="button session-reload" disabled={state.phase === 'busy'} onClick={() => { void controller.refresh().then(() => setReload(v => v + 1)) }}>Reload saved preparation</button>
  </>
}

function PreparationForm({ state, controller, onStarted }: { state: LearningState; controller: Controller; onStarted: () => void }) {
  const { controller: auth } = useAuth()
  const initialDraft = useRef(state.draft)
  const [step, setStep] = useState(0)
  const heading = useRef<HTMLHeadingElement>(null)
  const [purpose, setPurpose] = useState<Purpose>(state.draft ? purposeMap[state.draft.purpose] : 'custom')
  const custom = state.draft?.purpose === 'custom' ? state.draft.custom_purpose : null
  const [objective, setObjective] = useState(state.draft?.objective ?? '')
  const [revision, setRevision] = useState(state.draft?.revision ?? null)
  const [reviewed, setReviewed] = useState<{ id: string; revision: number } | null>(null)
  const [replacement, setReplacement] = useState<string | null>(null)
  const [reasoning] = useState(() => {
    const c = createReasoningController(ragApi, () => {}, auth.invalidate)
    const draft = state.draft
    if (draft) { draft.document_ids.forEach(id => c.select(id)); c.setMode(draft.mode); c.consent(draft.allow_context_transmission) }
    return c
  })
  const materials = useSyncExternalStore(reasoning.subscribe, reasoning.getSnapshot)
  useEffect(() => {
    const draft = initialDraft.current
    if (draft) {
      draft.document_ids.forEach(id => { if (!reasoning.getSnapshot().selected.includes(id)) reasoning.select(id) })
      reasoning.setMode(draft.mode)
      if (reasoning.getSnapshot().consent !== draft.allow_context_transmission) reasoning.consent(draft.allow_context_transmission)
    }
    void reasoning.refresh()
    return () => reasoning.dispose()
    // Restore the initial draft on effect replay; later edits remain local until saved.
  }, [reasoning])
  useEffect(() => { heading.current?.focus() }, [step])
  const busy = state.phase === 'busy'
  const objectiveValid = validPreparationObjective(objective, purpose)
  const purposeValid = Object.hasOwn(purposes, purpose)
  const input: PreparationInput = { revision, purpose, custom_purpose: purpose === 'custom' ? custom ?? purposes.custom : null, objective: objectiveFor(objective, purpose), document_ids: materials.selected, mode: materials.mode, allow_context_transmission: materials.consent }
  const save = async (review: boolean) => {
    const ok = await controller.save(input, review)
    const draft = controller.getSnapshot().draft
    if (draft) setRevision(draft.revision)
    if (ok && review && draft?.status === 'ready') { setReviewed({ id: draft.id, revision: draft.revision }); setStep(4) }
  }
  const reviewedCurrent = reviewed && state.draft?.id === reviewed.id && state.draft.revision === reviewed.revision && state.draft.status === 'ready'
  return <section className="session-preparation reveal" aria-labelledby="preparation-title" aria-busy={busy}>
    <header className="workspace-intro"><div><span className="eyebrow">SESSION PREPARATION</span><h1 id="preparation-title">Give your learning<br /><span className="luminous-text">a direction.</span></h1><p className="tagline">Choose a purpose, set your objective and review the context before you begin.</p></div></header>
    <ol className="preparation-steps" aria-label="Preparation progress">{steps.map((label, i) => <li key={label} aria-current={step === i ? 'step' : undefined}><span aria-hidden="true">0{i + 1}</span>{label}</li>)}<li><span aria-hidden="true">06</span>Start Session</li></ol>
    <fieldset className="preparation-panel" disabled={busy}><legend className="sr-only">Session preparation fields</legend>
      <h2 ref={heading} tabIndex={-1} className="preparation-step-title">{steps[step]}</h2>
      {step === 0 && <fieldset className="purpose-options" disabled={busy}><legend>What are you working toward?</legend>{Object.entries(purposes).map(([value, label]) => <label key={value} htmlFor={`purpose-${value}`} aria-label={label}><input id={`purpose-${value}`} name="session-purpose" type="radio" checked={purpose === value} onChange={() => setPurpose(value as Purpose)} /><span className="purpose-copy"><strong>{label}</strong><span className="capture-privacy">{purposeDescriptions[value as Purpose]}</span></span></label>)}<p className="capture-privacy">Purpose guides the learning experience; all purposes support multiple-choice, multiple-select, coding, essays, theoretical questions, mathematics and mixed questions.</p></fieldset>}
      {step === 1 && <div className="preparation-objective"><label htmlFor="learning-objective">What would you like to achieve?</label><textarea id="learning-objective" value={objective} maxLength={2000} rows={5} required={purpose !== 'custom'} aria-describedby="objective-help objective-count" onChange={e => setObjective(e.target.value)} /><p id="objective-help">For example: Help me understand Salesforce Sales Cloud certification questions and explain the recommended answers.</p><p id="objective-count" className="session-metadata">{objective.length} / 2000 characters · {purpose === 'custom' ? 'Optional · general assistance by default' : 'Required'}</p></div>}
      {(step === 2 || step === 3) && <ReasoningControls state={materials} controller={reasoning} stage={step === 2 ? 'materials' : 'mode'} />}
      {step === 4 && <div className="preparation-review"><dl><div><dt>Purpose</dt><dd>{purposes[purpose]}</dd></div><div><dt>Objective</dt><dd>{objectiveFor(objective, purpose)}</dd></div><div><dt>Reasoning mode</dt><dd>{materials.mode.replaceAll('_', ' ')}</dd></div><div><dt>Reference materials</dt><dd>{state.draft?.documents.length ? <ul>{state.draft.documents.map(d => <li key={d.id}>{d.title} · text {d.extraction_status} · index {d.index_status}</li>)}</ul> : 'No materials selected'}{state.draft?.missing_document_count ? <p role="alert">A selected document is missing. Review your selection.</p> : null}</dd></div><div><dt>Transmission</dt><dd>{materials.mode === 'general' ? 'General ignores documents. Only the observation and learning intent go to the answer provider.' : 'Selected relevant passages and learning intent may be sent to OpenAI for explicit answer requests. Passage transmission consent is recorded with this preparation.'}</dd></div></dl><p className="capture-privacy">Preparation metadata is saved for recovery. Screenshots, questions and generated answers remain ephemeral. Starting does not capture, index documents or call an AI provider.</p>{state.active && <label className="session-confirm"><input type="checkbox" checked={replacement === state.active.id} onChange={e => setReplacement(e.target.checked ? state.active?.id ?? null : null)} />End the active “{purposeLabel(state.active.purpose)}” session and replace it with this preparation.</label>}{!reviewedCurrent && <p role="status">This preparation changed. Go back and review it again before starting.</p>}</div>}
      {state.notice && <p className="session-metadata" role="status">{state.notice}</p>}
      {state.message && <p className="capture-error" role="alert">{state.message}</p>}
      <div className="preparation-actions"><button className="button" disabled={step === 0 || busy} onClick={() => setStep(s => s - 1)}>Back</button>{step < 4 && <button className="button" disabled={!purposeValid || !objectiveValid || busy} onClick={() => { void save(false) }}>Save Draft</button>}{step < 3 ? <button className="button button-primary" disabled={busy || (step === 0 && !purposeValid) || (step === 1 && !objectiveValid)} onClick={() => setStep(s => s + 1)}>Continue</button> : step === 3 ? <button className="button button-primary" disabled={busy || !purposeValid || !objectiveValid || !reasoning.ready()} onClick={() => { void save(true) }}>Review preparation</button> : <button className="button button-primary" disabled={busy || !reviewedCurrent || (!!state.active && replacement !== state.active.id)} onClick={() => { if (reviewed) void controller.start(reviewed, state.active ? replacement : null).then(ok => { if (ok) onStarted() }) }}>Start Session</button>}</div>
      {busy && <p role="status">Saving or updating session metadata…</p>}
    </fieldset>
  </section>
}
