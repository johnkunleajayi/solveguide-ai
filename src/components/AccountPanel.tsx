import { useAuth } from '../auth/context'
import { useId } from 'react'
import type { AuthState } from '../auth/types'

export function AccountContent({ state, onSignIn, onSignOut, onCancel, onRefresh }: { state: AuthState; onSignIn: () => void; onSignOut: () => void; onCancel: () => void; onRefresh: () => void }) {
  const user = state.user
  const titleId = useId()
  return <section className="account-panel" aria-labelledby={titleId}>
    <div><span className="eyebrow">YOUR ACCOUNT</span><h3 id={titleId}>A workspace of your own.</h3></div>
    {state.phase === 'checking' ? <p role="status">Checking account…</p> : state.phase === 'signing_out' ? <p role="status">Signing out…</p> : user ? <>
      <div className="account-identity"><span className="account-avatar" aria-hidden="true">{user.avatar_url?.startsWith('https://lh3.googleusercontent.com/') ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : user.display_name.slice(0, 1).toUpperCase()}</span><div><strong>{user.display_name}</strong><p>{user.email}</p></div></div>
      <button className="button" onClick={onSignOut}>Sign out</button>
    </> : state.phase === 'signing_in' ? <><p role="status">Finish signing in with Google in your browser. This window will update automatically.</p><button className="button" onClick={onCancel}>Cancel sign-in</button></> : state.phase === 'unavailable' ? <p role="status">Account access is unavailable. The learning workspace stays locked until your session can be checked.</p> : <>
      <p className="muted">Sign in securely with Google. Your captures and answers stay ephemeral.</p>
      <button className="button button-primary" onClick={onSignIn}>Sign in with Google <span aria-hidden="true">↗</span></button>
    </>}
    {state.message && <p className="capture-error" role="alert">{state.message}</p>}
    {(state.phase === 'error' || state.phase === 'unavailable') && !user && <button className="button" onClick={onRefresh}>Check connection</button>}
    <p className="account-privacy">Sign-in is required for learning tools. Accounts do not save questions, screenshots or answers. Local privacy and appearance settings remain available.</p>
  </section>
}

export function AccountPanel() {
  const { state, controller } = useAuth()
  return <AccountContent state={state} onSignIn={() => { void controller.signIn() }} onSignOut={() => { void controller.signOut() }} onCancel={() => { void controller.cancel() }} onRefresh={() => { void controller.check() }} />
}
