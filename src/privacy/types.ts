export type EffectiveState = 'enabled' | 'disabled' | 'unsupported' | 'failed'
export interface PrivacyStatus {
  supported: boolean | null
  preferenceEnabled: boolean
  effectiveState: EffectiveState
  preferencePersisted: boolean
  issue: 'unsupported_platform' | 'unsupported_version' | 'capability_unavailable' | 'invalid_window' | 'access_denied' | 'apply_failed' | 'read_failed' | 'verification_failed' | null
}
export interface PrivacyApi { get(): Promise<PrivacyStatus>; set(enabled: boolean): Promise<PrivacyStatus> }
export function parsePrivacyStatus(value: unknown): PrivacyStatus {
  if (typeof value !== 'object' || value === null) throw Error('Invalid privacy response')
  const data = value as Record<string, unknown>
  if (!(data.supported === null || typeof data.supported === 'boolean') || typeof data.preferenceEnabled !== 'boolean' || typeof data.preferencePersisted !== 'boolean'
    || !['enabled', 'disabled', 'unsupported', 'failed'].includes(String(data.effectiveState))
    || !(data.issue === null || ['unsupported_platform', 'unsupported_version', 'capability_unavailable', 'invalid_window', 'access_denied', 'apply_failed', 'read_failed', 'verification_failed'].includes(String(data.issue)))) throw Error('Invalid privacy response')
  const status = data as unknown as PrivacyStatus
  if ((status.effectiveState === 'enabled' && (!status.preferenceEnabled || status.supported !== true || status.issue !== null))
    || (status.effectiveState === 'disabled' && (status.preferenceEnabled || status.supported !== true || status.issue !== null))
    || (status.effectiveState === 'unsupported' && status.supported !== false)) throw Error('Inconsistent privacy response')
  return status
}
