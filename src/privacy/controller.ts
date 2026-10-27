import type { PrivacyApi, PrivacyStatus } from './types'
export interface PrivacyViewState { phase: 'checking' | 'ready' | 'updating' | 'error'; status: PrivacyStatus | null; message: string | null }
export function createPrivacyController(api: PrivacyApi) {
  let state: PrivacyViewState = { phase: 'checking', status: null, message: null }
  let generation = 0
  const listeners = new Set<() => void>()
  const publish = (next: PrivacyViewState) => { state = next; listeners.forEach(fn => fn()) }
  const request = async (enabled?: boolean) => {
    if (state.phase === 'updating') return
    const current = ++generation
    publish({ ...state, phase: enabled === undefined ? 'checking' : 'updating', message: null })
    try {
      const status = enabled === undefined ? await api.get() : await api.set(enabled)
      if (current === generation) publish({ phase: 'ready', status, message: null })
    } catch {
      if (current === generation) publish({ phase: 'error', status: null, message: 'Could not verify screen-share privacy. Protection is unconfirmed. Try again.' })
    }
  }
  return {
    getSnapshot: () => state,
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },
    refresh: () => request(),
    setEnabled: (enabled: boolean) => request(enabled),
    dispose() { ++generation; listeners.clear() },
  }
}
