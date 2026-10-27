import type { ReactNode } from 'react'
import type { AuthState } from '../auth/types'
import { workspaceAllowed } from '../auth/controller'
import { AccountPanel } from './AccountPanel'
export function AuthGate({ state, children }: { state: AuthState; children: ReactNode }) {
  return workspaceAllowed(state) ? children : <SignedOutShell />
}
export function SignedOutShell() {
  return <section className="sign-in-shell reveal" aria-labelledby="sign-in-title">
    <div className="sign-in-brand"><span className="eyebrow">SOLVEGUIDE AI · DESKTOP</span>
      <h1 id="sign-in-title">Understand the question.<br /><span className="luminous-text">Find the answer.</span><br />Learn why.</h1>
      <p className="muted">Sign in to continue. A focused workspace for learning, with clarity at every step.</p>
    </div>
    <div className="sign-in-card"><AccountPanel /><p className="account-privacy">Google authentication opens in your system browser. Screen-share privacy remains independent of sign-in and is available in Settings where supported.</p></div>
  </section>
}
