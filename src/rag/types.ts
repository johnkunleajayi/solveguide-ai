export type ReasoningMode = 'general' | 'context_guided' | 'materials_only'
export interface ReasoningOptions { mode: ReasoningMode; document_ids: string[]; allow_context_transmission: boolean; session?: { id: string; revision: number } }
export interface Citation { document_id: string; document_title: string; chunk_id: string; page_number: number | null; location: string; excerpt: string; supports: string[] }
export interface Grounding { reasoning_mode: Exclude<ReasoningMode, 'general'>; grounding_status: 'document_supported' | 'mixed' | 'general_reasoning' | 'insufficient_evidence'; retrieval_method: 'semantic_pgvector' | 'lexical' | 'none'; citations: Citation[]; general_reasoning: string[] }
export interface IndexedDocument { id: string; title: string; extraction_status: string; index_status: 'ready' | 'indexing' | 'failed' | 'not_indexed'; method: 'semantic_pgvector' | 'lexical' | null; error_code: string | null; generation: string | null }
export interface Catalog { documents: IndexedDocument[]; next_cursor: string | null; semantic_available: boolean }
export interface RagApi { list(cursor?: string, selected?: string[]): Promise<Catalog>; index(id: string, method: 'semantic_pgvector' | 'lexical', consent: boolean, force: boolean): Promise<void> }
