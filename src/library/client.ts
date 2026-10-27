import { invoke, isTauri } from '@tauri-apps/api/core'
import { parseDocument, type DocumentDetail, type LibraryApi, type LibraryLimits } from './types'
import { notifyLibraryChange } from './changes'

const messages: Record<string, string> = {
  context_consent_required: 'Explicit permission is required before selected document text is sent to OpenAI.',
  context_changed: 'Selected materials changed. Refresh readiness and retry.',
  index_busy: 'This document is already being indexed. Refresh readiness shortly.',
  index_failed: 'Indexing could not complete. Retry explicitly.',
  semantic_unavailable: 'Semantic retrieval is unavailable. Choose local lexical indexing.',
  embedding_not_configured: 'Configure the backend embedding provider before semantic indexing.',
  embedding_timeout: 'The embedding provider timed out. Retry indexing explicitly.',
  embedding_authentication: 'The embedding provider rejected backend credentials.',
  embedding_rate_limited: 'The embedding provider is busy. Retry later.',
  embedding_unavailable: 'The embedding provider is unavailable. Retry later.',

  unsupported_document: 'Choose a PDF, DOCX or TXT document.',
  document_too_large: 'The selected document exceeds the upload limit.',
  extraction_limit: 'This document exceeds the extraction limit. Try a smaller document.',
  invalid_document: 'This document could not be read. Check its format and text encoding.',
  invalid_request: 'Check the title and text, then try again.',
  document_unavailable: 'The selected file could not be opened. Try choosing it again.',
  document_not_found: 'This document is no longer available. Refresh your library.',
  storage_unavailable: 'Document storage is unavailable. If deleting, retry to finish removal.',
  deletion_pending: 'This document is pending deletion. Retry deleting it.',
  request_timeout: 'The document transfer timed out. Try again.',
}
export async function request(operation: object): Promise<unknown> {
  if (!isTauri()) throw { code: 'desktop_required' }
  try {
    const response = await invoke<{ ok: boolean; status: number; data?: unknown; error?: { code?: string } }>('library_request', { operation })
    if (!response.ok) throw { code: response.status === 401 ? 'sign_in_required' : response.error?.code ?? 'library_unavailable' }
    return response.data
  } catch (error) {
    const code = error && typeof error === 'object' && 'code' in error && typeof error.code === 'string' ? error.code : 'backend_unavailable'
    throw { code, message: messages[code] ?? 'The library request could not be completed. Check the backend connection and try again.' }
  }
}
const detail = (raw: unknown) => parseDocument(raw, true) as DocumentDetail
export const libraryApi: LibraryApi = {
  async list(cursor) {
    const raw = await request({ kind: 'list', cursor: cursor ?? null }) as { documents?: unknown[]; next_cursor?: unknown }
    if (!Array.isArray(raw?.documents) || !(raw.next_cursor === null || typeof raw.next_cursor === 'string')) throw Error('Invalid library page')
    return { documents: raw.documents.map(d => parseDocument(d)), next_cursor: raw.next_cursor }
  },
  async limits() {
    const raw = await request({ kind: 'limits' }) as LibraryLimits
    if (!raw || ![raw.upload_bytes, raw.text_characters, raw.pdf_pages].every(n => Number.isInteger(n) && n > 0)) throw Error('Invalid library limits')
    return raw
  },
  async upload() { const raw = await request({ kind: 'upload' }); return raw === null ? null : detail(raw) },
  async paste(title, text) { return detail(await request({ kind: 'paste', title, text })) },
  async detail(id) { return detail(await request({ kind: 'detail', id })) },
  async rename(id, title) { const result = detail(await request({ kind: 'rename', id, title })); notifyLibraryChange(id); return result },
  async delete(id) { await request({ kind: 'delete', id }); notifyLibraryChange(id) },
}
