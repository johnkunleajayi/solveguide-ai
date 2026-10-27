import type { CaptureController } from '../capture/controller'
import type { CaptureResult } from '../capture/types'
export function CapturePreview({ result, controller, onRead, reading }: { result: CaptureResult; controller: CaptureController; onRead: () => void; reading: boolean }) {
  return <div className="capture-preview">
    <figure><img src={`data:${result.format};base64,${result.imageBase64}`} alt={`Captured ${result.source.kind}: ${result.source.title}`} draggable={false} />
      <figcaption>This is what SolveGuide can see.</figcaption></figure>
    <p className="capture-source-caption"><strong>{result.source.kind === 'screen' ? 'Screen' : 'Window'}</strong> · {result.source.title}<br />{result.width} × {result.height} px · {new Date(result.capturedAt).toLocaleTimeString()}</p>
    <div className="capture-actions"><button className="button button-primary" disabled={reading} onClick={onRead}>{reading ? 'Reading question...' : 'Read Question'}</button><button className="button" onClick={() => void controller.retake()}>Retake</button><button className="button" onClick={() => void controller.open()}>Change Source</button><button className="button" onClick={() => controller.clear()}>Clear capture</button></div>
    <p className="capture-privacy" role="status">Read Question sends this capture to OpenAI through your local backend. Recommendations are a separate, explicit action.</p>
  </div>
}
