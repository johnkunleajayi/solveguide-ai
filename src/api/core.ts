import { invoke, isTauri } from '@tauri-apps/api/core'
export interface CoreResponse { ok: boolean; status: number; data?: unknown; error?: { code: string } }
export async function requestCore(kind: 'vision' | 'answer', payload: unknown, signal: AbortSignal): Promise<CoreResponse> {
  if (!isTauri()) throw { code: 'desktop_required', message: 'Use the SolveGuide desktop application.' }
  if (signal.aborted) throw signal.reason
  const requestId = crypto.randomUUID()
  return new Promise((resolve, reject) => {
    const cancel = () => {
      void invoke('ai_cancel', { requestId }).catch(() => {})
      reject(signal.reason ?? new DOMException('Request cancelled', 'AbortError'))
    }
    signal.addEventListener('abort', cancel, { once: true })
    void invoke<CoreResponse>('ai_request', { kind, requestId, payload }).then(response => {
      if (response.status === 401 && !['sign_in_required', 'invalid_session', 'session_expired', 'session_revoked'].includes(response.error?.code ?? '')) response = { ...response, error: { code: 'sign_in_required' } }
      resolve(response)
    }, error => {
      const code = typeof error === 'object' && error !== null && 'code' in error && typeof error.code === 'string' ? error.code : 'backend_unavailable'
      reject({ code, message: code === 'backend_unavailable' ? 'The SolveGuide backend is unavailable. Check the connection and retry.' : code === 'sign_in_required' ? 'Sign in to continue.' : 'The request could not be completed. Please try again.' })
    })
      .finally(() => signal.removeEventListener('abort', cancel))
  })
}
