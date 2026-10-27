import type { CaptureResult } from '../capture/types'
import type { QuestionObservation, VisionApi, VisionError } from './types'
export interface ObservationState {
  phase: 'idle' | 'reading' | 'ready' | 'error'
  observation: QuestionObservation | null
  error: VisionError | null
}
export function createObservationController(api: VisionApi) {
  let state: ObservationState = { phase: 'idle', observation: null, error: null }
  let generation = 0
  let pending: AbortController | null = null
  const listeners = new Set<() => void>()
  const update = (next: ObservationState) => { state = next; listeners.forEach(listener => listener()) }
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    reset() { ++generation; pending?.abort(); pending = null; update({ phase: 'idle', observation: null, error: null }) },
    async read(capture: CaptureResult) {
      if (state.phase === 'reading') return
      const current = ++generation
      pending = new AbortController()
      update({ phase: 'reading', observation: null, error: null })
      try {
        const observation = await api(capture, pending.signal)
        if (current === generation) update({ phase: 'ready', observation, error: null })
      } catch (error) {
        if (current !== generation) return
        const safeError = typeof error === 'object' && error !== null && 'code' in error && 'message' in error
          && typeof error.code === 'string' && typeof error.message === 'string'
          ? { code: error.code, message: error.message }
          : { code: 'vision_unavailable', message: 'Question reading failed. Please retry.' }
        update({ phase: 'error', observation: null, error: safeError })
      } finally { if (current === generation) pending = null }
    },
  }
}
