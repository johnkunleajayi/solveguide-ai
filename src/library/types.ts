export type ExtractionStatus = 'ready' | 'insufficient' | 'failed' | 'deleting'
export interface ContextDocument {
  id: string; title: string; original_filename: string | null
  document_type: 'pdf' | 'docx' | 'txt'; source_type: 'upload' | 'pasted_text'
  byte_size: number; extraction_status: ExtractionStatus; extraction_error: string | null
  character_count: number; created_at: string; updated_at: string
}
export interface DocumentDetail extends ContextDocument {
  extracted_text: string
  extraction_structure: { kind: 'page' | 'paragraph' | 'table' | 'text'; number: number; start: number; end: number }[]
}
export interface LibraryPage { documents: ContextDocument[]; next_cursor: string | null }
export interface LibraryLimits { upload_bytes: number; text_characters: number; pdf_pages: number }
export interface LibraryApi {
  list(cursor?: string): Promise<LibraryPage>
  limits(): Promise<LibraryLimits>
  upload(): Promise<DocumentDetail | null>
  paste(title: string, text: string): Promise<DocumentDetail>
  detail(id: string): Promise<DocumentDetail>
  rename(id: string, title: string): Promise<DocumentDetail>
  delete(id: string): Promise<void>
}
export interface LibraryState {
  phase: 'loading' | 'ready' | 'working'
  documents: ContextDocument[]; detail: DocumentDetail | null; cursor: string | null
  limits: LibraryLimits | null; error: string | null; notice: string | null
}

export function parseDocument(raw: unknown, detail = false): DocumentDetail | ContextDocument {
  if (!raw || typeof raw !== 'object') throw Error('Invalid document response')
  const d = raw as Record<string, unknown>
  if (typeof d.id !== 'string' || !/^[\da-f-]{36}$/i.test(d.id) || typeof d.title !== 'string' ||
    !['pdf', 'docx', 'txt'].includes(String(d.document_type)) || !['upload', 'pasted_text'].includes(String(d.source_type)) ||
    !['ready', 'insufficient', 'failed', 'deleting'].includes(String(d.extraction_status)) ||
    typeof d.character_count !== 'number' || d.character_count < 0 || typeof d.byte_size !== 'number' ||
    typeof d.created_at !== 'string' || typeof d.updated_at !== 'string' ||
    !(d.original_filename === null || typeof d.original_filename === 'string') ||
    !(d.extraction_error === null || typeof d.extraction_error === 'string')) throw Error('Invalid document response')
  if (detail && (typeof d.extracted_text !== 'string' || d.extracted_text.length > 2_000_000 || !Array.isArray(d.extraction_structure) ||
    !d.extraction_structure.every(s => s && ['page', 'paragraph', 'table', 'text'].includes(s.kind) && Number.isInteger(s.number) && s.number > 0 && Number.isInteger(s.start) && s.start >= 0 && Number.isInteger(s.end) && s.end >= s.start && s.end <= (d.extracted_text as string).length))) throw Error('Invalid document text')
  return raw as ContextDocument | DocumentDetail
}
