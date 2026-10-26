import { ArrowUpRight, Command, Settings2 } from 'lucide-react'
import { Brand } from './Brand'

interface Props { onOpenSettings: () => void }

export function Sidebar({ onOpenSettings }: Props) {
  return (
    <aside className="sidebar">
      <Brand />
      <nav className="main-nav" aria-label="Main navigation">
        <span className="nav-label">WORKSPACE</span>
        <a className="nav-item active" href="#main" aria-current="page" title="Learning workspace">
          <Command size={18} aria-hidden="true" />
          <span className="nav-text">Learning workspace</span>
          <span className="nav-indicator" aria-hidden="true" />
        </a>
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
