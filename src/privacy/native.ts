import { invoke, isTauri } from '@tauri-apps/api/core'
import { parsePrivacyStatus, type PrivacyApi, type PrivacyStatus } from './types'
const unsupported: PrivacyStatus = { supported: false, preferenceEnabled: true, effectiveState: 'unsupported', preferencePersisted: false, issue: 'unsupported_platform' }
export const privacyApi: PrivacyApi = {
  async get() { return isTauri() ? parsePrivacyStatus(await invoke('privacy_get_state')) : unsupported },
  async set(enabled) { return isTauri() ? parsePrivacyStatus(await invoke('privacy_set_enabled', { enabled })) : unsupported },
}
