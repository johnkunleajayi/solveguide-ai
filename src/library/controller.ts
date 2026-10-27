import type { DocumentDetail, LibraryApi, LibraryState } from './types'

export function createLibraryController(api: LibraryApi, onAccessFailure: (error: unknown) => void) {
  let state: LibraryState = { phase: 'loading', documents: [], detail: null, cursor: null, limits: null, error: null, notice: null }
  let generation = 0
  const listeners = new Set<() => void>()
  const publish = (patch: Partial<LibraryState>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()) }
  async function run(work: () => Promise<Partial<LibraryState>>, phase: LibraryState['phase'] = 'working') {
    if (state.phase === 'working') return false
    const current = ++generation
    publish({ phase, error: null, notice: null })
    try {
      const result = await work()
      if (current !== generation) return false
      publish({ ...result, phase: 'ready' }); return true
    } catch (error) {
      if (current !== generation) return false
      onAccessFailure(error)
      if (current !== generation) return false
      const message = error && typeof error === 'object' && 'message' in error && typeof error.message === 'string' ? error.message : 'Could not update the library. Please try again.'
      publish({ phase: 'ready', error: message }); return false
    }
  }
  async function created(action: () => Promise<DocumentDetail | null>) {
    const current = generation + 1
    return run(async () => {
      const document = await action()
      if (current !== generation) return {}
      if (!document) return { notice: 'File selection cancelled.' }
      const page = await api.list()
      return { documents: page.documents, cursor: page.next_cursor, detail: document, notice: 'Added to your reusable library. Select and index materials explicitly before using them in grounded answers.' }
    })
  }
  return {
    getSnapshot: () => state,
    subscribe(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } },
    load: () => run(async () => { const [page, limits] = await Promise.all([api.list(), api.limits()]); return { documents: page.documents, cursor: page.next_cursor, limits } }, 'loading'),
    more: () => run(async () => { const page = await api.list(state.cursor ?? undefined); return { documents: [...state.documents, ...page.documents], cursor: page.next_cursor } }),
    select: (id: string) => run(async () => ({ detail: await api.detail(id) })),
    upload: () => created(() => api.upload()),
    paste: (title: string, text: string) => created(() => api.paste(title, text)),
    rename: (id: string, title: string) => run(async () => {
      const detail = await api.rename(id, title)
      return { detail, documents: state.documents.map(d => d.id === id ? detail : d), notice: 'Title updated.' }
    }),
    delete: (id: string) => {
      const current = generation + 1
      return run(async () => {
        await api.delete(id)
        if (current !== generation) return {}
        const page = await api.list()
        return { documents: page.documents, cursor: page.next_cursor, detail: null, notice: 'Document and its stored content deleted.' }
      })
    },
    dispose() { ++generation; state = { ...state, documents: [], detail: null, cursor: null, error: null, notice: null }; listeners.clear() },
  }
}
