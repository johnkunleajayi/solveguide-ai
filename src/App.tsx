import { useState } from 'react'
import { Settings2 } from 'lucide-react'
import { AnswerWorkspace } from './components/AnswerWorkspace'
import { PointerLight } from './components/PointerLight'
import { SettingsDialog } from './components/SettingsDialog'
import { Sidebar } from './components/Sidebar'
import { usePointerPreference } from './hooks/usePointerPreference'
import { useTheme } from './hooks/useTheme'

export default function App() {
  const { theme, setTheme } = useTheme()
  const { pointerLight, setPointerLight } = usePointerPreference()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [captureOpen, setCaptureOpen] = useState(false)

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to workspace</a>
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} />
      <div className="main-shell">
        <header className="topbar">
          <span className="breadcrumb"><span>Workspace</span><span aria-hidden="true">/</span>Overview</span>
          <div className="topbar-actions"><span className="preview-label">DESKTOP PREVIEW</span>
            <button className="icon-button" aria-label="Open settings" title="Settings" onClick={() => setSettingsOpen(true)}>
              <Settings2 size={18} aria-hidden="true" />
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <AnswerWorkspace onCaptureModalChange={setCaptureOpen} />
          <footer className="workspace-footer reveal"><span><span className="signal-dot" aria-hidden="true" />Capture · Understand · Recommend · Explain</span><span>A little clarity changes everything.</span></footer>
        </main>
      </div>
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} theme={theme} setTheme={setTheme}
        pointerLight={pointerLight} setPointerLight={setPointerLight} />
      <PointerLight enabled={pointerLight && !settingsOpen && !captureOpen} />
    </div>
  )
}
