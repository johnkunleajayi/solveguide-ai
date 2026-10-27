import type { CaptureResult } from '../capture/types'
import { parseObservation, type VisionError } from './types'

const ENDPOINT = 'http://127.0.0.1:8000/api/v1/vision/question'
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const messages: Record<string, string> = {
  provider_not_configured: 'Set OPENAI_API_KEY in backend/.env, then restart the backend.',
  provider_authentication: 'The vision provider rejected the backend credentials. Review backend configuration.',
  provider_timeout: 'Reading the question timed out. Please retry.',
  provider_rate_limited: 'The vision provider is busy or its quota is unavailable. Try again later.',
  provider_unavailable: 'The backend could not reach the vision provider. Please retry.',
  vision_busy: 'Another question is being read. Please try again shortly.',
  invalid_image: 'The capture is damaged or incomplete. Please retake it.',
  invalid_image_type: 'Only single-frame PNG captures can be read.',
  image_too_large: 'This capture exceeds the 10 MiB or 40 megapixel limit. Choose a smaller source.',
  request_too_large: 'This capture is too large. Choose a smaller source.',
  invalid_provider_response: 'The provider could not return a valid observation. Retake or retry.',
}
export async function readQuestion(capture: CaptureResult, signal: AbortSignal) {
  if (capture.format !== 'image/png' || capture.imageBase64.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4) {
    throw { code: 'image_too_large', message: messages.image_too_large } satisfies VisionError
  }
  const timeout = AbortSignal.timeout(110_000)
  try {
    const response = await fetch(ENDPOINT, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ media_type: capture.format, image_base64: capture.imageBase64 }),
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.any([signal, timeout]),
    })
    const raw: unknown = await response.json()
    if (!response.ok) {
      const code = typeof raw === 'object' && raw !== null && 'error' in raw
        && typeof raw.error === 'object' && raw.error !== null && 'code' in raw.error
        && typeof raw.error.code === 'string' ? raw.error.code : 'vision_unavailable'
      throw { code, message: messages[code] ?? 'Question reading is unavailable. Retake or retry.' } satisfies VisionError
    }
    return parseObservation(raw)
  } catch (error) {
    if (signal.aborted) throw error
    if (timeout.aborted) throw { code: 'network_timeout', message: 'The backend request timed out. Please retry.' } satisfies VisionError
    if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) throw error
    throw { code: 'backend_unavailable', message: 'Could not reach the SolveGuide backend. Start it with npm.cmd run backend, then retry.' } satisfies VisionError
  }
}
