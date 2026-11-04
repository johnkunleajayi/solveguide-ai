import type { MonitorSnapshot, MonitorOperation } from './types'

/** UI-ready commit proxy only: browser monotonic duration, never a cross-process timestamp. */
export function createReadyReporter() {
  let last: string | null = null
  return (snapshot: MonitorSnapshot, now: number): MonitorOperation | null => {
    const timing = snapshot.localPerformance
    const metadata = snapshot.performance
    if (!metadata || !timing || !snapshot.answer || snapshot.phase !== 'answer_ready') return null
    const key = `${metadata.traceId}:${snapshot.generation}`
    const elapsed = now - timing.receivedAt
    if (key === last || !Number.isFinite(elapsed) || elapsed < 0 || elapsed > 300000 || !Number.isFinite(timing.validationMs) || timing.validationMs < 0 || timing.validationMs > 300000) return null
    last = key
    return { kind: 'performance_ready', generation: snapshot.generation, receipt_to_ready_ms: Math.round(elapsed), validation_ms: Math.round(timing.validationMs) }
  }
}
