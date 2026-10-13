import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, type Faq } from '../lib/api'
import { ui } from '../lib/ui'

export default function Faqs() {
  const [items, setItems] = useState<Faq[]>([])
  const [open, setOpen] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [category, setCategory] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => setItems(await api<Faq[]>('/faqs')), [])
  useEffect(() => {
    void load()
  }, [load])

  const reset = () => {
    setOpen(false)
    setEditId(null)
    setQuestion('')
    setAnswer('')
    setCategory('')
    setError('')
  }

  const startEdit = (f: Faq) => {
    setEditId(f.id)
    setQuestion(f.question)
    setAnswer(f.answer)
    setCategory(f.category ?? '')
    setOpen(true)
  }

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api(editId ? `/faqs/${editId}` : '/faqs', {
        method: editId ? 'PUT' : 'POST',
        body: JSON.stringify({ question, answer, category: category || null }),
      })
      reset()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (f: Faq) => {
    if (!confirm('Delete this FAQ?')) return
    await api(`/faqs/${f.id}`, { method: 'DELETE' })
    await load()
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">FAQs</h1>
        <button className={ui.btn} onClick={() => { reset(); setOpen(true) }}>Add FAQ</button>
      </div>

      {open && (
        <form onSubmit={save} className={`${ui.card} mt-4 space-y-3`}>
          <div>
            <label className={ui.label}>Question *</label>
            <input className={ui.input} value={question} onChange={(e) => setQuestion(e.target.value)} required />
          </div>
          <div>
            <label className={ui.label}>Answer *</label>
            <textarea className={ui.input} rows={3} value={answer} onChange={(e) => setAnswer(e.target.value)} required />
          </div>
          <div className="max-w-xs">
            <label className={ui.label}>Category</label>
            <input className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button disabled={busy} className={ui.btn}>{busy ? 'Saving...' : editId ? 'Save changes' : 'Create FAQ'}</button>
            <button type="button" className={ui.btnGhost} onClick={reset}>Cancel</button>
          </div>
        </form>
      )}

      <div className="mt-4 space-y-3">
        {items.map((f) => (
          <div key={f.id} className={ui.card}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-medium">{f.question}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{f.answer}</p>
                {f.category && <p className="mt-2 text-xs text-slate-400">{f.category}</p>}
              </div>
              <div className="flex shrink-0 gap-2">
                <button className={ui.btnGhost} onClick={() => startEdit(f)}>Edit</button>
                <button className={ui.btnDanger} onClick={() => void remove(f)}>Delete</button>
              </div>
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No FAQs yet.</p>}
      </div>
    </div>
  )
}
