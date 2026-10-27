// In-process invalidation only. No document content, storage or cross-session state.
const listeners = new Set<(id: string) => void>()
export function notifyLibraryChange(id: string) { listeners.forEach(listener => listener(id)) }
export function subscribeLibraryChanges(listener: (id: string) => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
