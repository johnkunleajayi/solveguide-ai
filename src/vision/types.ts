export const questionTypes = ['multiple_choice', 'multiple_select', 'true_false', 'short_answer', 'essay', 'mathematics', 'code', 'mixed', 'unknown'] as const
export const visualKinds = ['chart', 'diagram', 'table', 'screenshot', 'illustration', 'formula', 'code', 'other'] as const
export interface QuestionObservation {
  status: 'detected' | 'unclear' | 'no_question'
  question_type: typeof questionTypes[number]
  question_text: string | null
  options: { label: string; text: string }[]
  instructions: string[]
  required_selection_count: number | null
  visible_context: string[]
  visual_elements: { kind: typeof visualKinds[number]; description: string; text: string | null; language: string | null }[]
  extraction_confidence: number
  warnings: string[]
}
export interface VisionError { code: string; message: string }
export type VisionApi = (capture: import('../capture/types').CaptureResult, signal: AbortSignal) => Promise<QuestionObservation>

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 20000
const texts = (value: unknown, max: number): value is string[] => Array.isArray(value) && value.length <= max && value.every(text)
const nullableText = (value: unknown) => value === null || text(value)
const keys = (value: Record<string, unknown>, expected: string[]) => Object.keys(value).length === expected.length && expected.every(key => key in value)
/** Runtime guard for the IPC/HTTP boundary. Provider text is always rendered as text, never HTML. */
export function parseObservation(value: unknown): QuestionObservation {
  if (!record(value)
    || !keys(value, ['status', 'question_type', 'question_text', 'options', 'instructions', 'required_selection_count', 'visible_context', 'visual_elements', 'extraction_confidence', 'warnings'])
    || !['detected', 'unclear', 'no_question'].includes(String(value.status))
    || !questionTypes.some(type => type === value.question_type)
    || !nullableText(value.question_text) || !texts(value.instructions, 30)
    || !texts(value.visible_context, 30) || !texts(value.warnings, 30)
    || typeof value.extraction_confidence !== 'number' || !Number.isFinite(value.extraction_confidence)
    || value.extraction_confidence < 0 || value.extraction_confidence > 1
    || !(value.required_selection_count === null || (typeof value.required_selection_count === 'number' && Number.isInteger(value.required_selection_count) && value.required_selection_count >= 1 && value.required_selection_count <= 100))
    || !Array.isArray(value.options) || value.options.length > 100
    || !value.options.every(option => record(option) && keys(option, ['label', 'text']) && text(option.label) && option.label.length <= 40 && text(option.text))
    || !Array.isArray(value.visual_elements) || value.visual_elements.length > 40
    || !value.visual_elements.every(element => record(element) && keys(element, ['kind', 'description', 'text', 'language']) && visualKinds.some(kind => kind === element.kind) && text(element.description) && nullableText(element.text) && nullableText(element.language))) {
    throw { code: 'invalid_response', message: 'The question observation was invalid. Please retry.' } satisfies VisionError
  }
  const observation = value as unknown as QuestionObservation
  if ((observation.status === 'detected' && !observation.question_text)
    || (observation.status === 'unclear' && !observation.warnings.length)
    || (observation.status === 'no_question' && (observation.question_type !== 'unknown' || observation.question_text !== null || observation.options.length || observation.required_selection_count !== null))
    || new Set(observation.options.map(option => option.label)).size !== observation.options.length) {
    throw { code: 'invalid_response', message: 'The question observation was inconsistent. Please retry.' } satisfies VisionError
  }
  return observation
}
