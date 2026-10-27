import type { QuestionObservation } from '../vision/types'
import type { CaptureController } from '../capture/controller'
import type { createObservationController } from '../vision/controller'
import type { AnswerApi, AnswerError, AnswerRecommendation } from './types'
import type { ReasoningOptions } from '../rag/types'
export interface AnswerState { phase: 'idle' | 'loading' | 'ready' | 'error'; result: AnswerRecommendation | null; error: AnswerError | null }
export function createAnswerController(api: AnswerApi) {
  let state: AnswerState = { phase: 'idle', result: null, error: null }
  let generation = 0
  let pending: AbortController | null = null
  const listeners = new Set<() => void>()
  const update = (next: AnswerState) => { state = next; listeners.forEach(listener => listener()) }
  return {
    getSnapshot: () => state,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener) } },
    reset() { ++generation; pending?.abort(); pending = null; update({ phase: 'idle', result: null, error: null }) },
    async request(observation: QuestionObservation, options?: ReasoningOptions) {
      if (state.phase === 'loading') return
      const current = ++generation
      pending = new AbortController()
      update({ phase: 'loading', result: null, error: null })
      try {
        const result = await api(observation, pending.signal, options)
        if (current === generation) update({ phase: 'ready', result, error: null })
      } catch (error) {
        if (current !== generation) return
        const safe = typeof error === 'object' && error !== null && 'code' in error && 'message' in error && typeof error.code === 'string' && typeof error.message === 'string' ? { code: error.code, message: error.message } : { code: 'answer_unavailable', message: 'The recommendation failed. Try Again.' }
        update({ phase: 'error', result: null, error: safe })
      } finally { if (current === generation) pending = null }
    },
  }
}
/** Subscribe to the existing controllers: invalidation is synchronous, not deferred until paint. */
export function connectAnswerLifecycle(answer: ReturnType<typeof createAnswerController>, capture: CaptureController, observation: ReturnType<typeof createObservationController>) {
  let previousCapture = capture.getSnapshot()
  let previousObservation = observation.getSnapshot()
  const stopCapture = capture.subscribe(() => {
    const next = capture.getSnapshot()
    if (next.result !== previousCapture.result || (next.phase === 'selecting' && previousCapture.phase !== 'selecting')) answer.reset()
    previousCapture = next
  })
  const stopObservation = observation.subscribe(() => {
    const next = observation.getSnapshot()
    if (next.observation !== previousObservation.observation || next.phase === 'reading') answer.reset()
    previousObservation = next
  })
  return () => { stopCapture(); stopObservation(); answer.reset() }
}
