import { invoke, isTauri } from '@tauri-apps/api/core'
import { parseUser, type AuthApi } from './types'
const base = 'http://127.0.0.1:8000/api/v1/auth'
async function web(path: string, post = false) {
  const response = await fetch(base + path, { method: post ? 'POST' : 'GET', credentials: 'include', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15_000), ...(post ? { headers: { 'Content-Type': 'application/json' }, body: '{}' } : {}) })
  if (!response.ok) {
    const raw: unknown = await response.json()
    throw raw && typeof raw === 'object' && 'error' in raw ? raw.error : { code: 'auth_unavailable' }
  }
  return response.status === 204 ? null : response.json()
}
export const authApi: AuthApi = {
  async me() { return parseUser(isTauri() ? await invoke('auth_me') : await web('/me')) },
  async start() { if (isTauri()) await invoke('auth_start'); else window.location.assign(base + '/google/start') },
  async poll() { return parseUser(isTauri() ? await invoke('auth_poll') : await web('/me')) },
  async cancel() { if (isTauri()) await invoke('auth_cancel') },
  async logout() { if (isTauri()) await invoke('auth_logout'); else await web('/logout', true) },
}
