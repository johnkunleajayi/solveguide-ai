export const questionTypes = ['multiple_choice', 'multiple_select', 'true_false', 'short_answer', 'essay', 'mathematics', 'code', 'mixed', 'visual_reasoning', 'unknown'] as const
export const visualKinds = ['chart', 'diagram', 'table', 'screenshot', 'illustration', 'formula', 'code', 'other'] as const
export interface VisualTask {
  requested_output?: 'editing_prompt' | 'selection' | 'explanation' | null
  comparisons?: { element: string; property: 'text' | 'color' | 'spacing' | 'size' | 'position' | 'presence' | 'style'; original: string; edited: string; status: 'changed' | 'unchanged' | 'uncertain' }[]
  kind: 'editing_prompt' | 'odd_one_out' | 'sequence' | 'spot_difference' | 'mixed_visual'
  images: { identifier: string; position: string; role: 'original' | 'edited' | 'option' | 'sequence' | 'comparison' | 'unknown'; description: string }[]
  image_count: number
  complete: boolean
  direction: 'established' | 'ambiguous' | 'not_applicable'
  observed_changes: string[]
}
export interface QuestionObservation {
  visual_task?: VisualTask | null
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
function validVisualTask(value: unknown): value is VisualTask | null {
  if (value === null) return true
  if (!record(value) || !keys(value, ['kind', 'images', 'image_count', 'complete', 'direction', 'observed_changes', ...('requested_output' in value ? ['requested_output'] : []), ...('comparisons' in value ? ['comparisons'] : [])])
    || ('requested_output' in value && value.requested_output !== null && !['editing_prompt', 'selection', 'explanation'].includes(String(value.requested_output)))
    || ('comparisons' in value && (!Array.isArray(value.comparisons) || value.comparisons.length > 40 || !value.comparisons.every(row => record(row) && keys(row, ['element', 'property', 'original', 'edited', 'status'])
      && text(row.element) && row.element.length <= 160 && text(row.original) && row.original.length <= 500 && text(row.edited) && row.edited.length <= 500
      && ['text', 'color', 'spacing', 'size', 'position', 'presence', 'style'].includes(String(row.property)) && ['changed', 'unchanged', 'uncertain'].includes(String(row.status))
      && (row.status !== 'unchanged' || row.original === row.edited))))
    || !['editing_prompt', 'odd_one_out', 'sequence', 'spot_difference', 'mixed_visual'].includes(String(value.kind))
    || !['established', 'ambiguous', 'not_applicable'].includes(String(value.direction))
    || typeof value.complete !== 'boolean' || !Array.isArray(value.images) || value.images.length < 1 || value.images.length > 20
    || value.image_count !== value.images.length || !texts(value.observed_changes, 30) || value.observed_changes.some(s => s.length > 1200)
    || !value.images.every(image => record(image) && keys(image, ['identifier', 'position', 'role', 'description'])
      && text(image.identifier) && image.identifier.length <= 40 && text(image.position) && image.position.length <= 120
      && text(image.description) && image.description.length <= 4000
      && ['original', 'edited', 'option', 'sequence', 'comparison', 'unknown'].includes(String(image.role)))) return false
  const task = value as unknown as VisualTask
  return new Set(task.images.map(image => image.identifier)).size === task.images.length
    && new Set(task.comparisons?.map(row => `${row.element.trim().toLowerCase()}|${row.property}`)).size === (task.comparisons?.length ?? 0)
    && !((task.kind === 'editing_prompt' || task.requested_output === 'editing_prompt') && task.direction === 'established'
      && (task.images.filter(image => image.role === 'original').length !== 1 || task.images.filter(image => image.role === 'edited').length !== 1))
}
/** Runtime guard for the IPC/HTTP boundary. Provider text is always rendered as text, never HTML. */
export function parseObservation(value: unknown): QuestionObservation {
  if (!record(value)
    || !keys(value, ['status', 'question_type', 'question_text', 'options', 'instructions', 'required_selection_count', 'visible_context', 'visual_elements', 'extraction_confidence', 'warnings', ...('visual_task' in value ? ['visual_task'] : [])])
    || ('visual_task' in value && !validVisualTask(value.visual_task))
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
  const task = observation.visual_task
  if (task) {
    const choices = task.images.filter(image => image.role === 'option').map(image => image.identifier)
    if (observation.status === 'no_question' || (['odd_one_out', 'sequence'].includes(task.kind)
      && ((task.kind === 'odd_one_out' && choices.length < 2) || choices.length !== observation.options.length || observation.options.some(option => !choices.includes(option.label))))) {
      throw { code: 'invalid_response', message: 'The visual choices did not match the observation. Please retry.' } satisfies VisionError
    }
  }
  if ((observation.status === 'detected' && !observation.question_text)
    || (observation.status === 'unclear' && !observation.warnings.length)
    || (observation.status === 'no_question' && (observation.question_type !== 'unknown' || observation.question_text !== null || observation.options.length || observation.required_selection_count !== null))
    || new Set(observation.options.map(option => option.label)).size !== observation.options.length) {
    throw { code: 'invalid_response', message: 'The question observation was inconsistent. Please retry.' } satisfies VisionError
  }
  return task?.kind === 'mixed_visual' && task.requested_output === 'editing_prompt'
    ? { ...observation, visual_task: { ...task, kind: 'editing_prompt' } }
    : observation
}
