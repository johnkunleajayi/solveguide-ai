import { invoke, isTauri } from '@tauri-apps/api/core'
import type { CaptureApi, CaptureResult, CaptureSource } from './types'
export const nativeCapture: CaptureApi = {
  async listSources() {
    if (!isTauri()) throw new Error('Native desktop required')
    return invoke<CaptureSource[]>('list_capture_sources')
  },
  capture(source) {
    return invoke<CaptureResult>('capture_source', { request: { sourceId: source.id, kind: source.kind } })
  },
}
