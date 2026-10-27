import { ArrowUpRight, BookOpen, Command, Settings2 } from 'lucide-react'
import { Brand } from './Brand'

interface Props { onOpenSettings: () => void; libraryOpen: boolean; onNavigate: (library: boolean) => void }

export function Sidebar({ onOpenSettings, libraryOpen, onNavigate }: Props) {
  return (
    <aside className="sidebar">
      <Brand />
      <nav className="main-nav" aria-label="Main navigation">
        <span className="nav-label">WORKSPACE</span>
        <button className={'nav-item' + (!libraryOpen ? ' active' : '')} onClick={() => onNavigate(false)} aria-current={!libraryOpen ? 'page' : undefined} title="Learning workspace">
          <Command size={18} aria-hidden="true" />
          <span className="nav-text">Learning workspace</span>
          <span className="nav-indicator" aria-hidden="true" />
        </button>
        <button className={'nav-item' + (libraryOpen ? ' active' : '')} onClick={() => onNavigate(true)} aria-current={libraryOpen ? 'page' : undefined} title="Context Library">
          <BookOpen size={18} aria-hidden="true" /><span className="nav-text">Context Library</span>{libraryOpen && <span className="nav-indicator" aria-hidden="true" />}
        </button>
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-signature" aria-hidden="true">
          <span className="signature-line" />
          <p>Clarity starts<br />with a question.</p>
          <ArrowUpRight size={18} />
        </div>
        <button className="nav-item" onClick={onOpenSettings} title="Settings">
          <Settings2 size={18} aria-hidden="true" /><span className="nav-text">Settings</span>
        </button>
        <div className="version-label"><span>DESKTOP</span><span>V0.1.0</span></div>
      </div>
    </aside>
  )
}
