import { useEffect, useState, useSyncExternalStore } from 'react'
import { createPrivacyController, type PrivacyViewState } from '../privacy/controller'
import { privacyApi } from '../privacy/native'

export function PrivacyContent({ state, onSet, onRetry }: { state: PrivacyViewState; onSet: (enabled: boolean) => void; onRetry: () => void }) {
  const status = state.status
  const busy = state.phase === 'checking' || state.phase === 'updating'
  const labels = { enabled: 'Enabled · Windows affinity verified', disabled: 'Off · normal capture behavior', unsupported: 'Unavailable on this platform or Windows version', failed: 'Could not verify the requested protection state' }
  return <section className="privacy-settings" data-state={status?.effectiveState ?? state.phase} aria-labelledby="privacy-title">
    <h3 id="privacy-title" className="eyebrow">PRIVACY</h3>
    <div className="preference-row privacy-row">
      <div><label htmlFor="screen-share-privacy">Screen-share privacy</label><p id="screen-share-description">Keep SolveGuide out of supported screen captures and screen shares.</p></div>
      <input id="screen-share-privacy" className="switch" type="checkbox" role="switch" checked={status?.preferenceEnabled ?? true}
        disabled={busy || !status || status.supported === false} onChange={event => onSet(event.target.checked)}
        aria-describedby="screen-share-description screen-share-status" />
    </div>
    <p id="screen-share-status" className="privacy-status" role="status" aria-live="polite">{busy ? (state.phase === 'updating' ? 'Applying privacy preference…' : 'Checking native protection…') : state.message ?? (status ? labels[status.effectiveState] : 'Protection is unconfirmed.')}</p>
    {status && !status.preferencePersisted && status.issue !== 'unsupported_platform' && <p className="capture-error" role="alert">Your preference could not be saved. This change may not survive a restart.</p>}
    <p className="privacy-limit">Uses Windows capture protection where supported. This is a privacy feature, not a guarantee against every capture method.</p>
    {(state.phase === 'error' || status?.effectiveState === 'failed' || (status && !status.preferencePersisted && status.supported !== false)) && <button className="button" disabled={busy} onClick={status ? () => onSet(status.preferenceEnabled) : onRetry}>Retry privacy setting</button>}
  </section>
}

export function PrivacySettings({ active }: { active: boolean }) {
  const [controller] = useState(() => createPrivacyController(privacyApi))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => { if (active) void controller.refresh() }, [active, controller])
  useEffect(() => () => controller.dispose(), [controller])
  return <PrivacyContent state={state} onSet={enabled => { void controller.setEnabled(enabled) }} onRetry={() => { void controller.refresh() }} />
}
