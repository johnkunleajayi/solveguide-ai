import type { QuestionObservation } from '../vision/types'
import { parseAnswer, type AnswerError } from './types'
import { requestCore } from '../api/core'
const messages: Record<string, string> = {
  answer_not_configured: 'Set OPENAI_API_KEY in backend/.env, then restart the backend.',
  answer_authentication: 'The answer provider rejected the credentials. Review backend configuration.',
  answer_timeout: 'The suggested answer timed out. Please try again.',
  answer_unavailable: 'The backend could not reach the answer provider. Please try again.',
  answer_rate_limited: 'The answer provider is busy or its quota is unavailable. Try again later.',
  answer_busy: 'Another AI request is running. Please try again shortly.',
  selection_count_mismatch: 'The provider returned the wrong number of options. Try Again.',
  invalid_option_selection: 'The provider selected an option that was not observed. Try Again.',
  invalid_answer_response: 'The recommendation was incomplete or invalid. Try Again.',
  answer_type_mismatch: 'The recommendation did not match the question type. Try Again.',
  request_too_large: 'The observation is too large. Retake a more focused question.',
}
export async function getSuggestedAnswer(observation: QuestionObservation, signal: AbortSignal) {
  const timeout = AbortSignal.timeout(110_000)
  try {
    const response = await requestCore('answer', observation, AbortSignal.any([signal, timeout]))
    const raw: unknown = response.data
    if (!response.ok) {
      const code = response.status === 401 ? (response.error?.code ?? 'sign_in_required') : response.error?.code ?? 'answer_provider_error'
      throw { code, message: messages[code] ?? 'A recommendation could not be prepared. Please try again.' } satisfies AnswerError
    }
    return parseAnswer(raw, observation)
  } catch (error) {
    if (signal.aborted) throw error
    if (timeout.aborted) throw { code: 'answer_timeout', message: messages.answer_timeout } satisfies AnswerError
    if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) throw error
    throw { code: 'backend_unavailable', message: 'Could not reach the backend. Start npm.cmd run backend, then Try Again.' } satisfies AnswerError
  }
}
