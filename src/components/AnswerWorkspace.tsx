import { ArrowUpRight, ScanLine } from 'lucide-react'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { createCaptureController } from '../capture/controller'
import { nativeCapture } from '../capture/native'
import { CaptureDialog } from './CaptureDialog'
import { CapturePreview } from './CapturePreview'
import { createObservationController } from '../vision/controller'
import { readQuestion } from '../vision/client'
import { QuestionObservationView } from './QuestionObservationView'
import { createAnswerController, connectAnswerLifecycle } from '../answer/controller'
import { getSuggestedAnswer } from '../answer/client'
import { AnswerRecommendationView } from './AnswerRecommendationView'
import { useAuth } from '../auth/context'
import { authApi } from '../auth/client'
import { authenticatedCapture, connectWorkspaceAccess } from '../auth/workspace'
import { ReasoningControls } from './ReasoningControls'
import { createReasoningController } from '../rag/controller'
import { ragApi } from '../rag/client'
import { subscribeLibraryChanges } from '../library/changes'
import type { LearningSession } from '../learning/types'

export function AnswerWorkspace({ onCaptureModalChange, active = true, onOpenDocument, preparation }: { onCaptureModalChange: (open: boolean) => void; active?: boolean; preparation?: LearningSession; onOpenDocument?: (id: string) => void }) {
  const { controller: auth } = useAuth()
  const [protectedCapture] = useState(() => authenticatedCapture(nativeCapture, authApi, auth.invalidate))
  const [controller] = useState(() => createCaptureController(protectedCapture))
  const capture = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  const [observationController] = useState(() => createObservationController(readQuestion))
  const observation = useSyncExternalStore(observationController.subscribe, observationController.getSnapshot)
  const [answerController] = useState(() => createAnswerController(getSuggestedAnswer))
  const answer = useSyncExternalStore(answerController.subscribe, answerController.getSnapshot)
  const [reasoning] = useState(() => {
    const context = createReasoningController(ragApi, answerController.reset, auth.invalidate)
    if (preparation) { preparation.document_ids.forEach(id => context.select(id)); context.setMode(preparation.mode); context.consent(preparation.allow_context_transmission) }
    return context
  })
  const reasoningState = useSyncExternalStore(reasoning.subscribe, reasoning.getSnapshot)
  useEffect(() => subscribeLibraryChanges(id => {
    if ((preparation?.document_ids ?? reasoning.getSnapshot().selected).includes(id)) { answerController.reset(); void reasoning.refresh() }
  }), [reasoning, answerController, preparation])
  useEffect(() => {
    if (preparation) {
      preparation.document_ids.forEach(id => { if (!reasoning.getSnapshot().selected.includes(id)) reasoning.select(id) })
      reasoning.setMode(preparation.mode)
      if (reasoning.getSnapshot().consent !== preparation.allow_context_transmission) reasoning.consent(preparation.allow_context_transmission)
    }
    if (active) void reasoning.refresh()
  }, [active, reasoning, preparation])
  useEffect(() => {
    const refresh = () => { if (active) void reasoning.refresh() }
    window.addEventListener('focus', refresh)
    const timer = setInterval(refresh, 60_000)
    return () => { window.removeEventListener('focus', refresh); clearInterval(timer) }
  }, [active, reasoning])
  useEffect(() => () => reasoning.dispose(), [reasoning])
  useEffect(() => connectAnswerLifecycle(answerController, controller, observationController), [answerController, controller, observationController])
  useEffect(() => {
    protectedCapture.activate()
    const disconnect = connectWorkspaceAccess(controller, observationController, answerController, auth.invalidate)
    return () => { protectedCapture.close(); disconnect() }
  }, [controller, observationController, answerController, auth, protectedCapture])
  const requestAnswer = () => { if (observation.observation && (preparation ? preparation.ready : reasoning.ready())) void answerController.request(observation.observation, preparation ? {mode:preparation.mode,document_ids:preparation.document_ids,allow_context_transmission:preparation.allow_context_transmission,session:{id:preparation.id,revision:preparation.revision}} : reasoning.options()) }
  useEffect(() => {
    observationController.reset()
    return () => observationController.reset()
  }, [capture.result, observationController])
  const readCapture = () => { if (capture.result) void observationController.read(capture.result) }
  const modalOpen = capture.phase === 'selecting' || capture.phase === 'capturing'
  useEffect(() => { onCaptureModalChange(modalOpen); return () => onCaptureModalChange(false) }, [modalOpen, onCaptureModalChange])

  return (
    <>
      <section className="workspace-intro reveal" aria-labelledby="workspace-title">
        <div className="intro-copy">
          <span className="eyebrow"><span className="signal-dot" aria-hidden="true" />LEARNING, IN FOCUS</span>
          <h1 id="workspace-title">Understanding,<br />{' '}<span className="luminous-text">illuminated.</span></h1>
          <p className="tagline">Understand the question. Find the answer. Learn why.</p>
        </div>
        <div className="intro-action">
          <button className="button button-primary" onClick={() => void controller.open()} aria-describedby="analysis-availability">
            <ScanLine size={18} aria-hidden="true" />
            <span>Analyze Question</span>
            <ArrowUpRight size={17} aria-hidden="true" />
          </button>
          <p id="analysis-availability">Capture first. Read the question next.</p>
        </div>
      </section>

      <CaptureDialog state={capture} controller={controller} />
      <ol className="workflow-steps" aria-label="Learning workflow">
        <li aria-current={!capture.result ? 'step' : undefined}><span>01</span>Select Source &amp; Capture</li>
        <li aria-current={capture.result && observation.phase !== 'ready' ? 'step' : undefined}><span>02</span>Read Question</li>
        <li aria-current={observation.phase === 'ready' && !answer.result ? 'step' : undefined}><span>03</span>Get Suggested Answer</li>
        <li aria-current={answer.result ? 'step' : undefined}><span>04</span>Review explanation</li>
      </ol>
      {!preparation && <ReasoningControls state={reasoningState} controller={reasoning} />}

      <div className="workbench reveal" data-spotlight>
        <section className="question-panel" aria-labelledby="question-title">
          <header className="section-heading">
            <h2 id="question-title"><span className="section-index" aria-hidden="true">01</span>Question</h2>
            <span className="state-label">{capture.result ? 'Captured' : 'Awaiting capture'}</span>
          </header>
          {capture.result ? <CapturePreview result={capture.result} controller={controller} onRead={readCapture} reading={observation.phase === 'reading'} /> : <div className="question-empty">
            <span className="question-reticle" aria-hidden="true"><ScanLine size={26} strokeWidth={1} /></span>
            <h3>A question opens the way.</h3>
            <p>Your selected screen or window will appear here.</p>
          </div>}
          <div className="question-footnote"><span className="signal-dot" aria-hidden="true" />{capture.result ? 'Ephemeral capture · Not saved' : 'No capture selected'}</div>
        </section>

        <section className="result-panel" aria-labelledby="observation-title">
          <header className="section-heading">
            <h2 id="observation-title"><span className="section-index" aria-hidden="true">02</span>Question observation</h2>
            <span className="state-label">{observation.phase === 'ready' ? 'Read' : observation.phase === 'reading' ? 'Reading' : 'Not read'}</span>
          </header>
          <QuestionObservationView state={observation} onRetry={readCapture} onCancel={() => observationController.reset()} />
          <AnswerRecommendationView state={answer} observation={observation.observation} onRequest={requestAnswer} onCancel={() => answerController.reset()} onOpenDocument={onOpenDocument} enabled={observation.phase === 'ready' && capture.phase === 'preview' && (preparation ? preparation.ready : reasoning.ready())} />
        </section>

        <aside className="context-strip" aria-label="Context status">
          <span className="context-title"><span className="section-index" aria-hidden="true">04</span>Context</span>
          <span className="context-description">{(preparation?.mode ?? reasoningState.mode).replace('_', ' ')} · {(preparation?.document_ids ?? reasoningState.selected).length} selected</span>
          <span className="planned-label">Explicit selection · Ephemeral answers</span>
        </aside>
      </div>
    </>
  )
}



