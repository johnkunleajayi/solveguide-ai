export type SourceKind = 'screen' | 'window' | 'region'
export interface CaptureSource {
  id: string
  kind: SourceKind
  title: string
  width: number
  height: number
  x: number
  y: number
  primary: boolean
}
export interface CaptureResult {
  source: CaptureSource
  width: number
  height: number
  format: 'image/png'
  capturedAt: number
  imageBase64: string
}
export interface CaptureError { code: string; message: string }
export interface CaptureApi {
  listSources(): Promise<CaptureSource[]>
  capture(source: CaptureSource): Promise<CaptureResult>
}
export function captureError(value: unknown): CaptureError {
  if (typeof value === 'object' && value !== null && 'code' in value && 'message' in value
    && typeof value.code === 'string' && typeof value.message === 'string') {
    return { code: value.code, message: value.message }
  }
  return { code: 'native_unavailable', message: 'Native capture is available in the Windows desktop app. Please reopen SolveGuide or try again.' }
}
