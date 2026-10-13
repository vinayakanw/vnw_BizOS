import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type DocumentRow } from '../lib/api'
import { fileSize, ui } from '../lib/ui'

const badge: Record<string, string> = {
  uploaded: 'bg-slate-100 text-slate-700',
  processing: 'bg-amber-100 text-amber-800',
  ready: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-700',
}

export default function Documents() {
  const [items, setItems] = useState<DocumentRow[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => setItems(await api<DocumentRow[]>('/documents')), [])
  useEffect(() => {
    void load()
  }, [load])

  // Poll while anything is still being processed.
  const pending = items.some((d) => d.status === 'uploaded' || d.status === 'processing')
  useEffect(() => {
    if (!pending) return
    const t = setInterval(() => void load(), 2000)
    return () => clearInterval(t)
  }, [pending, load])

  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    setError('')
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData()
        fd.append('file', file)
        await api('/documents', { method: 'POST', body: fd })
      }
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  const retry = async (d: DocumentRow) => {
    await api(`/documents/${d.id}/reprocess`, { method: 'POST' })
    await load()
  }

  const remove = async (d: DocumentRow) => {
    if (!confirm(`Delete "${d.filename}"?`)) return
    await api(`/documents/${d.id}`, { method: 'DELETE' })
    await load()
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Documents</h1>
        <button className={ui.btn} disabled={busy} onClick={() => input.current?.click()}>
          {busy ? 'Uploading...' : 'Upload files'}
        </button>
        <input ref={input} type="file" multiple hidden accept=".pdf,.txt,.md,.docx,.csv" onChange={(e) => void upload(e.target.files)} />
      </div>
      <p className="mt-1 text-sm text-slate-500">
        PDF, DOCX, TXT, MD or CSV, up to 10 MB each. Uploaded files are read and indexed automatically. The first one can take a
        minute while the AI model downloads.
      </p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className={`${ui.card} mt-4 overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">File</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Passages</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-medium">{d.filename}</td>
                <td className="px-4 py-3">{fileSize(d.size_bytes)}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${badge[d.status] ?? badge.uploaded}`}>{d.status}</span>
                </td>
                <td className="px-4 py-3">{d.chunk_count}</td>
                <td className="px-4 py-3 text-slate-600">{new Date(d.created_at).toLocaleString()}</td>
                <td className="flex justify-end gap-2 px-4 py-3">
                  {(d.status === 'failed' || d.status === 'uploaded') && (
                    <button className={ui.btnGhost} onClick={() => void retry(d)}>Retry</button>
                  )}
                  <button className={ui.btnDanger} onClick={() => void remove(d)}>Delete</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">No documents yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
