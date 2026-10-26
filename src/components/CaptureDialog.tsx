import { useEffect, useRef } from 'react'
import { Monitor, AppWindow, Crop, X } from 'lucide-react'
import type { CaptureController, CaptureState } from '../capture/controller'

export function CaptureDialog({ state, controller }: { state: CaptureState; controller: CaptureController }) {
  const ref = useRef<HTMLDialogElement>(null)
  const open = state.phase === 'selecting' || state.phase === 'capturing'
  const busy = state.phase === 'capturing'
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return <dialog ref={ref} className="settings-dialog capture-dialog" aria-labelledby="capture-title" aria-describedby="capture-description"
    onCancel={event => { event.preventDefault(); controller.cancel() }}>
    <div className="dialog-content">
      <header className="dialog-header"><div><span className="eyebrow">NATIVE CAPTURE</span><h2 id="capture-title">Bring it into focus.</h2></div>
        <button className="icon-button" aria-label="Cancel capture" onClick={() => controller.cancel()}><X size={19} aria-hidden="true" /></button></header>
      <p id="capture-description" className="muted">Choose what SolveGuide should see. One frame, only when you ask.</p>
      <fieldset className="capture-types" disabled={busy}><legend className="sr-only">Capture source type</legend>
        {([{ kind: 'screen', label: 'Screen', Icon: Monitor }, { kind: 'window', label: 'Window', Icon: AppWindow }, { kind: 'region', label: 'Region', Icon: Crop }] as const).map(({ kind, label, Icon }) =>
          <label className="capture-type" key={kind} data-selected={state.kind === kind}><input type="radio" name="capture-type" checked={state.kind === kind} onChange={() => controller.chooseKind(kind)} /><Icon size={18} aria-hidden="true" /><span>{label}</span></label>)}
      </fieldset>
      <div role="status" aria-live="polite" className="capture-status">{busy ? 'Capturing one frame… Cancel discards the result.' : state.loading ? 'Finding available sources…' : state.kind === 'region' ? 'Region selection is coming next. Choose a screen or window for now.' : 'Select one source below.'}</div>
      {state.error && <p role="alert" className="capture-error">{state.error.message}</p>}
      {!busy && state.kind !== 'region' && <fieldset className="source-list" disabled={state.loading}><legend className="sr-only">Available {state.kind === 'screen' ? 'screens' : 'windows'}</legend>
        {state.sources.filter(source => source.kind === state.kind).map(source => <label className="source-option" htmlFor={`source-${source.id}`} key={source.id} data-selected={state.selected?.id === source.id}>
          <input id={`source-${source.id}`} aria-label={source.title} type="radio" name="capture-source" checked={state.selected?.id === source.id} onChange={() => controller.select(source)} />
          <span><strong>{source.title}</strong><small>{source.width} × {source.height} px · {source.kind === 'screen' && source.primary ? 'Primary · ' : ''}Position {source.x}, {source.y}</small></span>
        </label>)}
        {!state.loading && !state.error && !state.sources.some(source => source.kind === state.kind) && <p className="muted">No eligible sources found. Restore a window and refresh.</p>}
      </fieldset>}
      <div className="capture-actions"><button className="button" disabled={busy || state.loading} onClick={() => void controller.open()}>Refresh sources</button>
        <button className="button button-primary" disabled={!state.selected || busy || state.loading || state.kind === 'region'} onClick={() => void controller.capture()}>Capture {state.kind}</button></div>
      <p className="capture-privacy">Screen capture briefly hides SolveGuide. Stays in memory on this device. Nothing is uploaded or saved. Protected content may appear blank. AI analysis is not connected.</p>
    </div>
  </dialog>
}


