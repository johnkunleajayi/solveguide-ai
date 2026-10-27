import type { Catalog, RagApi, ReasoningMode, ReasoningOptions } from './types'
export function createReasoningController(api: RagApi, invalidate: () => void, denied: (error: unknown) => void) {
  let state = { mode: 'general' as ReasoningMode, selected: [] as string[], consent: false, embeddingConsent: false, catalog: { documents: [], semantic_available: false, next_cursor: null } as Catalog, busy: false, error: null as string | null }
  let generation = 0
  const listeners = new Set<() => void>()
  const update = (patch: Partial<typeof state>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()) }
  const signature = () => JSON.stringify(state.catalog.documents.filter(d => state.selected.includes(d.id)))
  const failure = (error: unknown) => { denied(error); update({ busy: false, error: error && typeof error === 'object' && 'message' in error && typeof error.message === 'string' ? error.message : 'Could not update document readiness. Refresh or retry. Provider indexing may require backend configuration or explicit consent.' }) }
  return {
    getSnapshot: () => state,
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },
    setMode(mode: ReasoningMode) { if (state.mode !== mode) { invalidate(); update({ mode }) } },
    select(id: string) { if (!state.selected.includes(id) && state.selected.length >= 5) return; invalidate(); update({ selected: state.selected.includes(id) ? state.selected.filter(v => v !== id) : [...state.selected, id] }) },
    consent(value: boolean) { invalidate(); update({ consent: value }) },
    embeddingConsent(value: boolean) { update({ embeddingConsent: value }) },
    async refresh(more = false) {
      if (state.busy) return
      const current = ++generation; const before = signature()
      try {
        const catalog = await api.list(more ? state.catalog.next_cursor ?? undefined : undefined)
        if (current !== generation) return
        const missing = state.selected.filter(id => !catalog.documents.some(d => d.id === id))
        if (!more && missing.length) {
          const chosen = await api.list(undefined, missing)
          if (current !== generation) return
          catalog.documents.push(...chosen.documents)
          for (const id of missing) if (!catalog.documents.some(d => d.id === id)) catalog.documents.push({ id, title: 'Unavailable document · deselect to continue', extraction_status: 'unavailable', index_status: 'not_indexed', method: null, generation: null, error_code: null })
        }
        update({ catalog: { ...catalog, documents: [...new Map([...(more ? state.catalog.documents : []), ...catalog.documents].map(d => [d.id, d])).values()] }, error: null })
        if (before !== signature()) invalidate()
      } catch (error) { if (current === generation) { invalidate(); failure(error) } }
    },
    async index(id: string, semantic: boolean) {
      if (state.busy) return
      invalidate(); const current = ++generation
      update({ busy: true, error: null })
      try { await api.index(id, semantic ? 'semantic_pgvector' : 'lexical', semantic && state.embeddingConsent, true); if (current !== generation) return; update({ busy: false }); await this.refresh() }
      catch (error) { if (current === generation) failure(error) }
    },
    options(): ReasoningOptions { return { mode: state.mode, document_ids: state.mode === 'general' ? [] : [...state.selected], allow_context_transmission: state.consent } },
    ready() { return state.mode === 'general' || (!state.error && state.consent && state.selected.length > 0 && state.selected.every(id => state.catalog.documents.some(d => d.id === id && d.index_status === 'ready' && d.extraction_status === 'ready')) && !state.busy) },
    dispose() { ++generation; state = { ...state, selected: [], consent: false, embeddingConsent: false, catalog: { documents: [], semantic_available: false, next_cursor: null } }; listeners.clear() },
  }
}
