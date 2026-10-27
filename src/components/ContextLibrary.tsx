import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { BookOpen, FileText, Plus, RefreshCw, Trash2, Upload, X } from 'lucide-react'
import { useAuth } from '../auth/context'
import { libraryApi } from '../library/client'
import { createLibraryController } from '../library/controller'
import type { LibraryState } from '../library/types'

type Controller = ReturnType<typeof createLibraryController>
export function ContextLibrary({ onModalChange }: { onModalChange: (open: boolean) => void }) {
  const { controller: auth } = useAuth()
  const [controller] = useState(() => createLibraryController(libraryApi, auth.invalidate))
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot)
  useEffect(() => { void controller.load(); return () => controller.dispose() }, [controller])
  return <LibraryContent state={state} controller={controller} onModalChange={onModalChange} />
}
const statusText = { ready: 'Text ready', insufficient: 'No readable text · OCR unavailable', failed: 'Extraction unavailable', deleting: 'Deletion pending · retry removal' }
export function LibraryContent({ state, controller, onModalChange }: { state: LibraryState; controller: Controller; onModalChange: (open: boolean) => void }) {
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [rename, setRename] = useState('')
  const [confirm, setConfirm] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  const busy = state.phase !== 'ready'
  const document = state.detail
  const deleteDocument = () => {
    setConfirm(false)
    if (document) void controller.delete(document.id).then(ok => { if (ok) addButton.current?.focus() })
  }
  useEffect(() => { onModalChange(confirm || state.phase === 'working'); return () => onModalChange(false) }, [confirm, state.phase, onModalChange])
  useEffect(() => { if (confirm && !dialog.current?.open) dialog.current?.showModal(); if (!confirm) dialog.current?.close() }, [confirm])
  return <section className="context-library reveal" aria-labelledby="library-title" aria-busy={busy}>
    <header className="library-heading"><div><span className="eyebrow">YOUR REFERENCE SHELF</span><h1 id="library-title">Context Library<span className="luminous-text">.</span></h1><p>Keep the material you want to return to.</p></div>
      <div className="library-actions"><button className="button library-secondary" onClick={() => setAdding(!adding)} disabled={busy} aria-expanded={adding}><Plus size={16} aria-hidden="true" />Paste text</button><button ref={addButton} className="button button-primary" onClick={() => { void controller.upload() }} disabled={busy}><Upload size={16} aria-hidden="true" />Add document</button></div>
    </header>
    <p className="library-privacy">Materials you add are saved privately to your account’s library. Current answers do not use them, and they are not sent to an AI provider.</p>
    <p className="library-limits">PDF · DOCX · TXT{state.limits && <> · Up to {Math.round(state.limits.upload_bytes / 1024 / 1024)} MiB per file · {state.limits.text_characters.toLocaleString()} extracted characters · {state.limits.pdf_pages} PDF pages</>}. Machine-readable text only; OCR is not available.</p>
    <div role="status" aria-live="polite" className="library-status">{state.phase === 'loading' ? 'Opening your library…' : state.phase === 'working' ? 'Working with your document…' : state.notice}</div>
    {state.error && <div role="alert" className="library-error"><p>{state.error}</p><button className="button library-secondary" disabled={busy} onClick={() => { void controller.load() }}><RefreshCw size={15} aria-hidden="true" />Refresh library</button></div>}
    {adding && <form className="library-form" onSubmit={event => { event.preventDefault(); void controller.paste(title, text).then(ok => { if (ok) { setAdding(false); setTitle(''); setText('') } }) }}>
      <div className="library-section-heading"><h2>Add your notes</h2><button type="button" className="icon-button" aria-label="Close pasted text" onClick={() => setAdding(false)} disabled={busy}><X size={17} aria-hidden="true" /></button></div>
      <label htmlFor="library-note-title">Title</label><input id="library-note-title" value={title} onChange={e => setTitle(e.target.value)} required maxLength={200} disabled={busy} placeholder="A useful name for these notes" />
      <label htmlFor="library-note-text">Plain text</label><textarea id="library-note-text" value={text} onChange={e => setText(e.target.value)} required maxLength={state.limits?.text_characters ?? 500_000} disabled={busy} rows={7} />
      <button className="button button-primary" disabled={busy || !title.trim() || !text.trim()}>Save to library</button>
    </form>}
    {state.phase === 'ready' && !state.documents.length && !state.error && <div className="library-empty"><BookOpen size={28} strokeWidth={1} aria-hidden="true" /><h2>A place for what you’re learning.</h2><p>Add study guides, course notes or reference documents.<br />They’ll stay in your library across sessions.</p><span>Live captures, questions and answers remain ephemeral.</span></div>}
    <div className="library-columns">
      <div className="library-list" aria-label="Your documents">{state.documents.map(item => <button key={item.id} className="library-document" aria-pressed={document?.id === item.id} onClick={() => { setRename(''); void controller.select(item.id) }} disabled={busy}>
        <FileText size={19} aria-hidden="true" /><span><strong>{item.title}</strong><small>{item.document_type.toUpperCase()} · {statusText[item.extraction_status]}</small></span><span className="library-count">{item.character_count.toLocaleString()} chars</span>
      </button>)}{state.cursor && <button className="button library-secondary" disabled={busy} onClick={() => { void controller.more() }}>Load more documents</button>}</div>
      {document && <article className="library-preview" aria-labelledby="document-title"><div className="library-section-heading"><span className="eyebrow">DOCUMENT DETAIL</span><button className="icon-button" aria-label="Delete document" disabled={busy} onClick={() => setConfirm(true)}><Trash2 size={17} aria-hidden="true" /></button></div>
        <h2 id="document-title">{document.title}</h2><p className="library-metadata">{document.document_type.toUpperCase()} · {document.source_type === 'upload' ? 'Uploaded document' : 'Pasted notes'} · {document.character_count.toLocaleString()} characters</p><p className="library-metadata">Added {new Date(document.created_at).toLocaleDateString()} · {statusText[document.extraction_status]}</p>
        {document.original_filename && <p className="library-metadata">Original: {document.original_filename}</p>}
        <form className="library-rename" key={document.id} onSubmit={event => { event.preventDefault(); void controller.rename(document.id, rename).then(ok => { if (ok) setRename('') }) }}><label htmlFor="library-rename-title">Rename title</label><div><input id="library-rename-title" value={rename} placeholder={document.title} maxLength={200} required disabled={busy || document.extraction_status === 'deleting'} onChange={e => setRename(e.target.value)} /><button className="button library-secondary" disabled={busy || !rename.trim() || document.extraction_status === 'deleting'}>Save title</button></div></form>
        {document.extraction_status === 'ready' ? <><h3>Extracted text</h3><textarea className="library-extracted" readOnly aria-label="Extracted document text" value={document.extracted_text} rows={14} /><p className="library-metadata">{document.extraction_structure.length} structural boundaries retained. Text is a deterministic extraction; review it against your original.</p></> : <p className="library-extraction-note">{document.extraction_status === 'insufficient' ? 'No machine-readable text was found. Scanned or image-only material needs OCR, which is not available yet.' : document.extraction_status === 'deleting' ? 'Deletion has started. Retry removal to finish deleting the stored file and metadata.' : 'This document could not be extracted safely. You can remove it and try a supported, unencrypted document.'}</p>}
      </article>}
    </div>
    <dialog ref={dialog} className="settings-dialog library-delete-dialog" aria-labelledby="library-delete-title" aria-describedby="library-delete-description" onClose={() => setConfirm(false)}>
      <div className="dialog-content"><h2 id="library-delete-title">Delete this document?</h2><p id="library-delete-description">This removes the library record, extracted text and stored original. This cannot be undone.</p><div className="library-actions"><button className="button library-secondary" onClick={() => setConfirm(false)}>Keep document</button><button className="button button-primary" onClick={deleteDocument}>Delete document</button></div></div>
    </dialog>
  </section>
}
