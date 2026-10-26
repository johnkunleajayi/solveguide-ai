import { captureError, type CaptureApi, type CaptureError, type CaptureResult, type CaptureSource, type SourceKind } from './types'
export interface CaptureState {
  phase: 'idle' | 'selecting' | 'capturing' | 'preview'
  kind: SourceKind
  sources: CaptureSource[]
  selected: CaptureSource | null
  result: CaptureResult | null
  loading: boolean
  error: CaptureError | null
}
/** Single-frame state machine. Cancellation invalidates pending replies; never retains history. */
export function createCaptureController(api: CaptureApi) {
  let state: CaptureState = { phase: 'idle', kind: 'screen', sources: [], selected: null, result: null, loading: false, error: null }
  let generation = 0
  const listeners = new Set<() => void>()
  const update = (patch: Partial<CaptureState>) => { state = { ...state, ...patch }; listeners.forEach(listener => listener()) }
  const controller = {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    async open() {
      const current = ++generation
      update({ phase: 'selecting', sources: [], selected: null, loading: true, error: null })
      try {
        const sources = await api.listSources()
        if (current === generation) update({ sources, loading: false })
      } catch (error) { if (current === generation) update({ error: captureError(error), loading: false }) }
    },
    chooseKind(kind: SourceKind) { update({ kind, selected: null, error: null }) },
    select(source: CaptureSource) { if (source.kind === state.kind && state.sources.includes(source)) update({ selected: source, error: null }) },
    cancel() { ++generation; update({ phase: state.result ? 'preview' : 'idle', loading: false, error: null }) },
    async capture(source = state.selected) {
      if (!source || source.kind === 'region' || state.loading || state.phase === 'capturing') return
      const current = ++generation
      update({ phase: 'capturing', selected: source, result: null, error: null })
      try {
        const result = await api.capture(source)
        if (current === generation) update({ phase: 'preview', result, selected: result.source })
      } catch (error) {
        if (current === generation) update({ phase: 'selecting', selected: null, error: captureError(error) })
      }
    },
    retake() { return controller.capture(state.result?.source) },
    clear() { ++generation; update({ phase: 'idle', result: null, selected: null, sources: [], error: null, loading: false }) },
  }
  return controller
}
export type CaptureController = ReturnType<typeof createCaptureController>

