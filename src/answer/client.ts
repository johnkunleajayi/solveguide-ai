import type { QuestionObservation } from '../vision/types'
import { parseAnswer, type AnswerError } from './types'
import { requestCore } from '../api/core'
import { parseGroundedAnswer } from '../rag/client'
import type { ReasoningOptions } from '../rag/types'
const messages: Record<string, string> = {
  session_changed: 'The session changed or ended. Refresh your active session.',
  session_required: 'Recover the active session before requesting an answer.',
  preparation_changed: 'The session revision changed. Refresh the workspace.',
  session_materials_changed: 'Session materials changed or are not ready. End this session and prepare again.',
  context_changed: 'Selected materials changed. Refresh readiness and request a new answer.',
  context_consent_required: 'Allow selected passage transmission before a grounded answer.',
  document_not_found: 'A selected document is no longer available. Refresh and review the selection.',
  embedding_timeout: 'Question retrieval timed out. Retry explicitly.',
  embedding_unavailable: 'Semantic retrieval is unavailable. Try again later.',
  embedding_not_configured: 'The embedding provider needs backend configuration.',

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
export async function getSuggestedAnswer(observation: QuestionObservation, signal: AbortSignal, options?: ReasoningOptions) {
  const timeout = AbortSignal.timeout(110_000)
  try {
    const grounded = options && options.mode !== 'general'
    const response = await requestCore('answer', options?.session ? {observation,session_id:options.session.id,session_revision:options.session.revision} : grounded ? { observation, ...options } : observation, AbortSignal.any([signal, timeout]))
    const raw: unknown = response.data
    if (!response.ok) {
      const code = response.status === 401 ? (response.error?.code ?? 'sign_in_required') : response.error?.code ?? 'answer_provider_error'
      throw { code, message: messages[code] ?? 'A recommendation could not be prepared. Please try again.' } satisfies AnswerError
    }
    return grounded ? parseGroundedAnswer(raw, observation, options) : parseAnswer(raw, observation)
  } catch (error) {
    if (signal.aborted) throw error
    if (timeout.aborted) throw { code: 'answer_timeout', message: messages.answer_timeout } satisfies AnswerError
    if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) throw error
    throw { code: 'backend_unavailable', message: 'Could not reach the backend. Start npm.cmd run backend, then Try Again.' } satisfies AnswerError
  }
}
