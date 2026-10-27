import type { QuestionObservation } from '../vision/types'
export interface AnswerRecommendation {
  status: 'answered' | 'uncertain' | 'insufficient_information' | 'unsupported'
  question_type: QuestionObservation['question_type']
  selected_options: string[]
  answer_text: string | null
  true_false_answer: boolean | null
  code_answer: { language: string | null; code: string } | null
  explanation: string
  key_points: string[]
  confidence: number
  warnings: string[]
}
export interface AnswerError { code: string; message: string }
export type AnswerApi = (observation: QuestionObservation, signal: AbortSignal) => Promise<AnswerRecommendation>
const record = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.trim().length > 0 && v.length <= max
const texts = (v: unknown, max: number, length: number): v is string[] => Array.isArray(v) && v.length <= length && v.every(s => text(s, max))
const keys = (v: Record<string, unknown>, expected: string[]) => Object.keys(v).length === expected.length && expected.every(k => k in v)
export function parseAnswer(value: unknown, observation: QuestionObservation): AnswerRecommendation {
  const invalid = () => { throw { code: 'invalid_answer_response', message: 'The recommendation did not match the observed question. Try Again.' } satisfies AnswerError }
  if (!record(value) || !keys(value, ['status', 'question_type', 'selected_options', 'answer_text', 'true_false_answer', 'code_answer', 'explanation', 'key_points', 'confidence', 'warnings'])
    || !['answered', 'uncertain', 'insufficient_information', 'unsupported'].includes(String(value.status))
    || value.question_type !== observation.question_type || !texts(value.selected_options, 40, 100)
    || !(value.answer_text === null || text(value.answer_text, 8000))
    || !(value.true_false_answer === null || typeof value.true_false_answer === 'boolean')
    || !(value.code_answer === null || (record(value.code_answer) && keys(value.code_answer, ['language', 'code']) && text(value.code_answer.code, 12000) && (value.code_answer.language === null || text(value.code_answer.language, 80))))
    || !text(value.explanation, 8000) || !texts(value.key_points, 1200, 8) || !texts(value.warnings, 2000, 30)
    || typeof value.confidence !== 'number' || !Number.isFinite(value.confidence) || value.confidence < 0 || value.confidence > 1) return invalid()
  const result = value as unknown as AnswerRecommendation
  if (new Set(result.selected_options).size !== result.selected_options.length || result.selected_options.some(label => !observation.options.some(option => option.label === label))) return invalid()
  const hasAnswer = result.answer_text !== null || result.code_answer !== null || result.true_false_answer !== null
  if (result.status !== 'answered' && !result.warnings.length) return invalid()
  if (result.status === 'insufficient_information' || result.status === 'unsupported') {
    if (hasAnswer || result.selected_options.length || result.key_points.length || result.confidence !== 0) return invalid()
    return result
  }
  if (!hasAnswer) {
    if (result.status === 'answered' || result.selected_options.length || result.key_points.length || result.confidence !== 0) return invalid()
    return result
  }
  if ((observation.question_type === 'true_false') !== (result.true_false_answer !== null)) return invalid()
  if (observation.options.length || ['multiple_choice', 'multiple_select'].includes(observation.question_type)) {
    const expected = ['multiple_choice', 'true_false'].includes(observation.question_type) ? 1 : observation.required_selection_count
    if (!result.selected_options.length || (expected !== null && result.selected_options.length !== expected)) return invalid()
    if (observation.question_type === 'true_false') {
      const chosen = observation.options.find(option => option.label === result.selected_options[0])?.text.trim().toLowerCase().replace(/\.$/, '')
      if ((chosen === 'true' || chosen === 'false') && (chosen === 'true') !== result.true_false_answer) return invalid()
    }
  } else if (result.selected_options.length) return invalid()
  return result
}
