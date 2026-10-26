import { ArrowUpRight, ScanLine } from 'lucide-react'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { createCaptureController } from '../capture/controller'
import { nativeCapture } from '../capture/native'
import { CaptureDialog } from './CaptureDialog'
import { CapturePreview } from './CapturePreview'

export function AnswerWorkspace({ onCaptureModalChange }: { onCaptureModalChange: (open: boolean) => void }) {
  const [controller] = useState(() => createCaptureController(nativeCapture))
  const capture = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
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
          <p id="analysis-availability">Capture first. AI analysis comes later.</p>
        </div>
      </section>

      <CaptureDialog state={capture} controller={controller} />

      <div className="workbench reveal" data-spotlight>
        <section className="question-panel" aria-labelledby="question-title">
          <header className="section-heading">
            <h2 id="question-title"><span className="section-index" aria-hidden="true">01</span>Question</h2>
            <span className="state-label">{capture.result ? 'Captured' : 'Awaiting capture'}</span>
          </header>
          {capture.result ? <CapturePreview result={capture.result} controller={controller} /> : <div className="question-empty">
            <span className="question-reticle" aria-hidden="true"><ScanLine size={26} strokeWidth={1} /></span>
            <h3>A question opens the way.</h3>
            <p>Your selected screen or window will appear here.</p>
          </div>}
          <div className="question-footnote"><span className="signal-dot" aria-hidden="true" />{capture.result ? 'Ephemeral capture · Not saved' : 'No capture selected'}</div>
        </section>

        <section className="result-panel" aria-labelledby="answer-title">
          <header className="section-heading">
            <h2 id="answer-title"><span className="section-index" aria-hidden="true">02</span>Suggested answer</h2>
            <span className="state-label">Empty</span>
          </header>
          <div className="answer-empty">
            <span className="answer-beam" aria-hidden="true" />
            <span className="eyebrow">SPACE FOR UNDERSTANDING</span>
            <h3>The answer is<br />only the beginning.</h3>
            <p>A suggested answer will appear here.<br />The reasoning will follow.</p>
          </div>
          <section className="explanation-area" aria-labelledby="explanation-title">
            <h2 id="explanation-title"><span className="section-index" aria-hidden="true">03</span>Explanation</h2>
            <p>A concise explanation will help you understand why.</p>
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



