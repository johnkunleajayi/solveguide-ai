import { request } from '../library/client'
import { parseAnswer, type AnswerRecommendation } from '../answer/types'
import type { QuestionObservation } from '../vision/types'
import type { Catalog, Grounding, RagApi, ReasoningOptions } from './types'
export const ragApi: RagApi = {
  async list(cursor, selected) {
    const raw = await request({ kind: 'index_list', cursor: cursor ?? null, selected: selected ?? null }) as Catalog
    if (!raw || !Array.isArray(raw.documents) || typeof raw.semantic_available !== 'boolean' || !(raw.next_cursor === null || typeof raw.next_cursor === 'string') || !raw.documents.every(d => typeof d.id === 'string' && typeof d.title === 'string' && ['ready', 'indexing', 'failed', 'not_indexed'].includes(d.index_status) && typeof d.extraction_status === 'string' && (d.generation === null || typeof d.generation === 'string'))) throw Error('Invalid indexing response')
    return raw
  },
  async index(id, method, consent, force) { await request({ kind: 'index', id, method, consent, force }) },
}
export function parseGroundedAnswer(raw: unknown, observation: QuestionObservation, options: ReasoningOptions): AnswerRecommendation {
  const invalid = () => { throw { code: 'invalid_answer_response', message: 'The sources or grounding could not be validated. Try Again.' } }
  if (!raw || typeof raw !== 'object') return invalid()
  const { reasoning_mode, grounding_status, retrieval_method, citations, general_reasoning, ...base } = raw as Grounding & Record<string, unknown>
  const answer = parseAnswer(base, observation)
  if (reasoning_mode !== options.mode || !['document_supported', 'mixed', 'insufficient_evidence'].includes(grounding_status) || !['semantic_pgvector', 'lexical', 'none'].includes(retrieval_method) || !Array.isArray(citations) || citations.length > 10 || !Array.isArray(general_reasoning) || general_reasoning.length > 8 || !general_reasoning.every(v => typeof v === 'string' && v.length <= 1200) || (options.mode === 'materials_only' && general_reasoning.length)) return invalid()
  const seen = new Set<string>()
  for (const c of citations) {
    if (!c || !options.document_ids.includes(c.document_id) || typeof c.chunk_id !== 'string' || !/^[\da-f-]{36}$/i.test(c.chunk_id) || seen.has(c.chunk_id) || typeof c.document_title !== 'string' || typeof c.location !== 'string' || typeof c.excerpt !== 'string' || !c.excerpt.trim() || c.excerpt.length > 3200 || !(c.page_number === null || (Number.isInteger(c.page_number) && c.page_number > 0)) || !Array.isArray(c.supports) || !c.supports.length || !c.supports.every(s => ['answer', 'explanation', ...answer.key_points.map((_, i) => `key_point:${i}`)].includes(s))) return invalid()
    seen.add(c.chunk_id)
  }
  if (grounding_status === 'insufficient_evidence' && (answer.status !== 'insufficient_information' || citations.length || general_reasoning.length)) return invalid()
  if (['answered', 'uncertain'].includes(answer.status) && !citations.length) return invalid()
  if (options.mode === 'materials_only' && ['answered', 'uncertain'].includes(answer.status)) {
    const covered = new Set(citations.flatMap(c => c.supports))
    if (grounding_status !== 'document_supported' || retrieval_method === 'none' || !['answer', 'explanation', ...answer.key_points.map((_, i) => `key_point:${i}`)].every(target => covered.has(target))) return invalid()
  }
  return { ...answer, grounding: { reasoning_mode, grounding_status, retrieval_method, citations, general_reasoning } }
}
