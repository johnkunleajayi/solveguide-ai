import { ArrowUpRight, ScanLine } from 'lucide-react'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { createCaptureController } from '../capture/controller'
import { nativeCapture } from '../capture/native'
import { CaptureDialog } from './CaptureDialog'
import { CapturePreview } from './CapturePreview'
import { createObservationController } from '../vision/controller'
import { readQuestion } from '../vision/client'
import { QuestionObservationView } from './QuestionObservationView'

export function AnswerWorkspace({ onCaptureModalChange }: { onCaptureModalChange: (open: boolean) => void }) {
  const [controller] = useState(() => createCaptureController(nativeCapture))
  const capture = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  const [observationController] = useState(() => createObservationController(readQuestion))
  const observation = useSyncExternalStore(observationController.subscribe, observationController.getSnapshot)
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
          <h1 id="workspace-title">Understanding,<br /><span className="luminous-text">illuminated.</span></h1>
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
          <section className="explanation-area" aria-labelledby="explanation-title">
            <h2 id="explanation-title"><span className="section-index" aria-hidden="true">03</span>Answer generation</h2>
            <p>SolveGuide does not yet determine or recommend the correct answer.</p>
          </section>
        </section>

        <aside className="context-strip" aria-label="Context status">
          <span className="context-title"><span className="section-index" aria-hidden="true">04</span>Context</span>
          <span className="context-description">No materials connected</span>
          <span className="planned-label">Context Library · Planned</span>
        </aside>
      </div>
    </>
  )
}



