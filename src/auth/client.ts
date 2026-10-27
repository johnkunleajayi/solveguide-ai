import { invoke, isTauri } from '@tauri-apps/api/core'
import { parseUser, type AuthApi } from './types'
function desktop() { if (!isTauri()) throw { code: 'desktop_required' } }
export const authApi: AuthApi = {
  async me() { desktop(); return parseUser(await invoke('auth_me')) },
  async start() { desktop(); await invoke('auth_start') },
  async poll() { desktop(); return parseUser(await invoke('auth_poll')) },
  async cancel() { desktop(); await invoke('auth_cancel') },
  async logout() { desktop(); await invoke('auth_logout') },
}
