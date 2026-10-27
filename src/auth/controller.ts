import type { AuthApi, AuthState } from './types'
const messages: Record<string, string> = {
  database_not_configured: 'Account sign-in needs DATABASE_URL in the backend configuration.',
  database_unavailable: 'The account database is unavailable. Please try again.',
  database_schema: 'Apply the backend Alembic migrations before signing in.',
  auth_not_configured: 'Google sign-in is not configured on this backend yet.',
  session_expired: 'Your session expired. Sign in again.',
  session_revoked: 'Your session was signed out. Sign in again.',
  invalid_session: 'Please sign in again.',
  invalid_exchange: 'Sign-in expired. Start again.',
  google_sign_in_failed: 'Google sign-in was cancelled or could not be verified. Start again.',
  sign_in_required: 'Sign in to use SolveGuide.',
  backend_unavailable: 'The SolveGuide backend is unavailable. Check the connection and retry.',
  desktop_required: 'Open the SolveGuide desktop application to sign in.',
}
function failure(error: unknown) {
  const code = typeof error === 'object' && error !== null && 'code' in error && typeof error.code === 'string' ? error.code : ''
  return { code, message: messages[code] ?? 'Could not complete sign-in. Check the backend connection and try again.' }
}
export function accessFailure(error: unknown): boolean {
  const { code } = failure(error)
  return ['sign_in_required', 'session_expired', 'session_revoked', 'invalid_session', 'backend_unavailable', 'database_unavailable', 'database_schema', 'database_not_configured', 'desktop_required'].includes(code)
}
export function workspaceAllowed(state: AuthState): boolean { return state.phase === 'signed_in' && state.user !== null }
export function createAuthController(api: AuthApi, schedule = (fn: () => void) => setTimeout(fn, 2000), unschedule = (id: ReturnType<typeof setTimeout>) => clearTimeout(id)) {
  let state: AuthState = { phase: 'checking', user: null, message: null }
  let generation = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  const listeners = new Set<() => void>()
  const publish = (next: AuthState) => { state = next; listeners.forEach(fn => fn()) }
  const stop = () => { if (timer !== undefined) unschedule(timer); timer = undefined; ++generation }
  return {
    getSnapshot: () => state,
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },
    async check() {
      if (state.phase === 'signing_in' || state.phase === 'signing_out') return
      const current = ++generation
      try { const user = await api.me(); if (current === generation) publish({ phase: user ? 'signed_in' : 'signed_out', user, message: null }) }
      catch (error) { if (current === generation) { const safe = failure(error); publish({ phase: ['sign_in_required', 'invalid_session', 'session_expired', 'session_revoked'].includes(safe.code) ? 'signed_out' : 'unavailable', user: null, message: safe.message }) } }
    },
    async signIn() {
      if (state.phase === 'signing_in' || state.phase === 'signing_out' || state.user) return
      stop(); const current = generation; const deadline = Date.now() + 600_000
      publish({ phase: 'signing_in', user: null, message: null })
      const failed = (error: unknown) => { if (current === generation) publish({ phase: 'error', user: null, message: failure(error).message }) }
      const poll = async () => {
        if (current !== generation) return
        if (Date.now() > deadline) { failed({ code: 'invalid_exchange' }); void api.cancel().catch(() => {}); return }
        try {
          const user = await api.poll()
          if (current !== generation) return
          if (user) publish({ phase: 'signed_in', user, message: null })
          else timer = schedule(() => { void poll() })
        } catch (error) { failed(error) }
      }
      try { await api.start(); if (current === generation) timer = schedule(() => { void poll() }) }
      catch (error) { failed(error) }
    },
    async cancel() { stop(); publish({ phase: 'signed_out', user: null, message: null }); try { await api.cancel() } catch { /* Local state is already cleared. */ } },
    async signOut() {
      stop(); const current = generation
      publish({ phase: 'signing_out', user: null, message: null })
      try { await api.logout(); if (current === generation) publish({ phase: 'signed_out', user: null, message: null }) }
      catch { if (current === generation) publish({ phase: 'unavailable', user: null, message: 'Signed out on this device. Server revocation could not be confirmed; its session will expire normally. Check the backend connection.' }) }
    },
    invalidate(error: unknown) {
      if (!accessFailure(error)) return
      stop()
      const safe = failure(error)
      publish({ phase: ['sign_in_required', 'invalid_session', 'session_expired', 'session_revoked'].includes(safe.code) ? 'signed_out' : 'unavailable', user: null, message: safe.message })
    },
    dispose() { stop(); listeners.clear() },
  }
}
