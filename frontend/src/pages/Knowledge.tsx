import { useState, type FormEvent } from 'react'
import { api, type SearchHit } from '../lib/api'
import { ui } from '../lib/ui'

export default function Knowledge() {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const search = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      setHits(await api<SearchHit[]>('/knowledge/search', { method: 'POST', body: JSON.stringify({ query, top_k: 5 }) }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setBusy(false)
    }
  }

  const reindex = async () => {
    setNote('')
    setError('')
    try {
      const r = await api<{ documents: number; faqs: number }>('/knowledge/reindex', { method: 'POST' })
      setNote(`Re-indexing ${r.documents} documents and ${r.faqs} FAQs in the background.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reindex failed')
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Search what the AI knows</h1>
        <button className={ui.btnGhost} onClick={() => void reindex()}>Re-index everything</button>
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Test what the AI can find in your documents and FAQs. This is exactly what the Sales Agent will retrieve.
      </p>
      {note && <p className="mt-2 text-sm text-green-600">{note}</p>}

      <form onSubmit={search} className="mt-4 flex gap-2">
        <input className={ui.input} placeholder="e.g. What is your refund policy?" value={query} onChange={(e) => setQuery(e.target.value)} required />
        <button disabled={busy} className={ui.btn}>{busy ? 'Searching...' : 'Search'}</button>
      </form>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 space-y-3">
        {hits?.map((h) => (
          <div key={h.chunk_id} className={ui.card}>
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>
                {h.source_type === 'faq' ? 'FAQ' : 'Document'}: <span className="font-medium text-slate-700">{h.title}</span>
              </span>
              <span>match {(h.score * 100).toFixed(0)}%</span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm">{h.content}</p>
          </div>
        ))}
        {hits && hits.length === 0 && (
          <p className="py-8 text-center text-sm text-slate-500">Nothing indexed yet. Upload a document or add an FAQ first.</p>
        )}
      </div>
    </div>
  )
}
