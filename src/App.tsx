import { useState } from 'react'
import { Settings2 } from 'lucide-react'
import { AnswerWorkspace } from './components/AnswerWorkspace'
import { PointerLight } from './components/PointerLight'
import { SettingsDialog } from './components/SettingsDialog'
import { Sidebar } from './components/Sidebar'
import { usePointerPreference } from './hooks/usePointerPreference'
import { useTheme } from './hooks/useTheme'
import { AuthProvider, useAuth } from './auth/context'
import { workspaceAllowed } from './auth/controller'
import { AuthGate } from './components/AuthGate'
import { ContextLibrary } from './components/ContextLibrary'

export default function App() {
  return <AuthProvider><Application /></AuthProvider>
}
function Application() {
  const { state } = useAuth()
  const authenticated = workspaceAllowed(state)
  const { theme, setTheme } = useTheme()
  const { pointerLight, setPointerLight } = usePointerPreference()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [captureOpen, setCaptureOpen] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [libraryModal, setLibraryModal] = useState(false)

  return (
    <div className={authenticated ? 'app-shell' : 'auth-app-shell'}>
      <a className="skip-link" href="#main">Skip to workspace</a>
      {authenticated && <Sidebar libraryOpen={libraryOpen} onNavigate={setLibraryOpen} onOpenSettings={() => setSettingsOpen(true)} />}
      <div className="main-shell">
        <header className="topbar">
          <span className="breadcrumb">{authenticated ? <><span>Workspace</span><span aria-hidden="true">/</span>{libraryOpen ? 'Context Library' : 'Overview'}</> : <span>SolveGuide AI · Account access</span>}</span>
          <div className="topbar-actions"><span className="preview-label">DESKTOP PREVIEW</span>
            <button className="icon-button" aria-label="Open settings" title="Settings" onClick={() => setSettingsOpen(true)}>
              <Settings2 size={18} aria-hidden="true" />
            </button>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          <AuthGate state={state}>
            <div hidden={libraryOpen}><AnswerWorkspace key={state.user?.id} onCaptureModalChange={setCaptureOpen} /></div>
            {libraryOpen && <ContextLibrary key={state.user?.id} onModalChange={setLibraryModal} />}
            <footer className="workspace-footer reveal"><span><span className="signal-dot" aria-hidden="true" />Capture · Understand · Recommend · Explain</span><span>A little clarity changes everything.</span></footer>
          </AuthGate>
        </main>
      </div>
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} theme={theme} setTheme={setTheme}
        pointerLight={pointerLight} setPointerLight={setPointerLight} />
      <PointerLight enabled={pointerLight && !settingsOpen && !captureOpen && !libraryModal} />
    </div>
  )
}
