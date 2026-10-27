import type { CaptureApi } from '../capture/types'
import type { CaptureController } from '../capture/controller'
import type { createObservationController } from '../vision/controller'
import type { createAnswerController } from '../answer/controller'
import type { AuthApi } from './types'
import { accessFailure } from './controller'
/** Product-level preflight, independent of the native capture engine. */
export function authenticatedCapture(api: CaptureApi, auth: Pick<AuthApi, 'me'>, invalidate: (error: unknown) => void): CaptureApi & { activate(): void; close(): void } {
  let active = true
  let generation = 0
  const guard = async <T,>(run: () => Promise<T>) => {
    const current = generation
    try {
      if (!active) throw new DOMException('Workspace closed', 'AbortError')
      if (!await auth.me()) throw { code: 'sign_in_required', message: 'Sign in to continue.' }
      if (!active || current !== generation) throw new DOMException('Workspace closed', 'AbortError')
      return await run()
    } catch (error) { if (accessFailure(error)) invalidate(error); throw error }
  }
  return { listSources: () => guard(() => api.listSources()), capture: source => guard(() => api.capture(source)),
    activate() { active = true }, close() { active = false; ++generation } }
}
export function connectWorkspaceAccess(capture: CaptureController, observation: ReturnType<typeof createObservationController>, answer: ReturnType<typeof createAnswerController>, invalidate: (error: unknown) => void) {
  const inspect = () => {
    for (const error of [observation.getSnapshot().error, answer.getSnapshot().error]) if (error && accessFailure(error)) invalidate(error)
  }
  const stops = [observation.subscribe(inspect), answer.subscribe(inspect)]
  return () => { stops.forEach(stop => stop()); capture.clear(); observation.reset(); answer.reset() }
}
