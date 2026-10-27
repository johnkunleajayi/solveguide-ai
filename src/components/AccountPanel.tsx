import { useEffect, useState, useSyncExternalStore } from 'react'
import { authApi } from '../auth/client'
import { createAuthController } from '../auth/controller'
import type { AuthState } from '../auth/types'

export function AccountContent({ state, onSignIn, onSignOut, onCancel, onRefresh }: { state: AuthState; onSignIn: () => void; onSignOut: () => void; onCancel: () => void; onRefresh: () => void }) {
  const user = state.user
  return <section className="account-panel" aria-labelledby="account-title">
    <div><span className="eyebrow">YOUR ACCOUNT</span><h3 id="account-title">A workspace of your own.</h3></div>
    {state.phase === 'checking' ? <p role="status">Checking account…</p> : user ? <>
      <div className="account-identity"><span className="account-avatar" aria-hidden="true">{user.avatar_url?.startsWith('https://lh3.googleusercontent.com/') ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : user.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.display_name}</strong><p>{user.email}</p></div></div>
      <button className="button" onClick={onSignOut}>Sign out</button>
    </> : state.phase === 'signing_in' ? <><p role="status">Finish signing in with Google in your browser. This window will update automatically.</p><button className="button" onClick={onCancel}>Cancel sign-in</button></> : <>
      <p className="muted">Sign in securely with Google. Your captures and answers stay ephemeral.</p>
      <button className="button button-primary" onClick={onSignIn}>Sign in with Google <span aria-hidden="true">↗</span></button>
    </>}
    {state.message && <p className="capture-error" role="alert">{state.message}</p>}
    {state.phase === 'error' && !user && <button className="button" onClick={onRefresh}>Check connection</button>}
    <p className="account-privacy">Accounts do not save questions, screenshots or answers. Local learning tools remain available without sign-in.</p>
  </section>
}

export function AccountPanel() {
  const [controller] = useState(() => createAuthController(authApi))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => {
    void controller.check()
    const refresh = () => { void controller.check() }
    window.addEventListener('focus', refresh)
    return () => { window.removeEventListener('focus', refresh); controller.dispose() }
  }, [controller])
  return <AccountContent state={state} onSignIn={() => { void controller.signIn() }} onSignOut={() => { void controller.signOut() }} onCancel={() => { void controller.cancel() }} onRefresh={() => { void controller.check() }} />
}
