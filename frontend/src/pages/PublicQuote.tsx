import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { money } from '../lib/ui'

// Public quote page. No login: the long random link is the credential.
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type View = {
  business: string
  customer_name: string | null
  number: string
  items: { product: string; unit_price: number; quantity: number; line_total: number }[]
  currency: string
  subtotal: number
  discount_pct: number
  total: number
  status: 'sent' | 'accepted' | 'declined' | 'changes_requested' | 'expired'
  customer_response: string | null
  customer_note: string | null
  expires_at: string | null
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/public/quote${path}`, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!res.ok) {
    let detail = 'Something went wrong. Please try again.'
    try {
      const d = await res.json()
      if (typeof d.detail === 'string') detail = d.detail
    } catch {
      /* ignore */
    }
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return res.json() as Promise<T>
}

const DONE: Record<string, { title: string; text: string; cls: string }> = {
  accepted: { title: 'Quote accepted', text: 'Thank you! The team has been told and will contact you to confirm the order and payment.', cls: 'bg-green-50 text-green-900 ring-green-200' },
  declined: { title: 'Quote declined', text: 'Thanks for letting us know. If something changes, just message us in the chat.', cls: 'bg-slate-100 text-slate-800 ring-slate-200' },
  changes_requested: { title: 'Changes requested', text: 'Thanks. The team will review your request and send a revised quote.', cls: 'bg-amber-50 text-amber-900 ring-amber-200' },
  expired: { title: 'This quote has expired', text: 'Please contact us for an updated quote.', cls: 'bg-slate-100 text-slate-800 ring-slate-200' },
}

export default function PublicQuote() {
  const { token = '' } = useParams()
  const [q, setQ] = useState<View | null>(null)
  const [missing, setMissing] = useState(false)
  const [mode, setMode] = useState<'accept' | 'decline' | 'changes' | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    call<View>(`/${token}`).then(setQ).catch(() => setMissing(true))
  }, [token])

  const send = async (action: 'accept' | 'decline' | 'changes') => {
    setBusy(true)
    setError('')
    try {
      setQ(await call<View>(`/${token}/respond`, { method: 'POST', body: JSON.stringify({ action, note }) }))
      setMode(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  if (missing) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-center text-slate-600">
        <div>
          <p className="text-lg font-semibold text-slate-800">This quote link is not valid</p>
          <p className="mt-1 text-sm">Please check the link in your email or chat, or contact the business.</p>
        </div>
      </div>
    )
  }
  if (!q) return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">Loading...</div>

  const done = DONE[q.status]
  const open = q.status === 'sent'
  return (
    <div className="min-h-screen bg-slate-50 px-4 py-8">
      <div className="mx-auto max-w-xl">
        <p className="text-sm text-slate-500">{q.business}</p>
        <h1 className="mt-1 text-2xl font-semibold">Quote {q.number}</h1>
        {q.customer_name && <p className="mt-1 text-sm text-slate-600">Prepared for {q.customer_name}</p>}

        <div className="mt-5 rounded-2xl bg-white p-5 ring-1 ring-slate-200">
          <div className="divide-y divide-slate-100 text-sm">
            {q.items.map((it, i) => (
              <div key={i} className="flex justify-between gap-3 py-3">
                <div>
                  <p className="font-medium">{it.product}</p>
                  <p className="text-slate-500">{it.quantity} x {money(it.unit_price, q.currency)}</p>
                </div>
                <p className="font-medium">{money(it.line_total, q.currency)}</p>
              </div>
            ))}
          </div>
          <div className="mt-2 space-y-1 border-t border-slate-200 pt-3 text-sm">
            {q.discount_pct > 0 && (
              <>
                <div className="flex justify-between text-slate-600"><span>Subtotal</span><span>{money(q.subtotal, q.currency)}</span></div>
                <div className="flex justify-between text-slate-600"><span>Discount ({q.discount_pct}%)</span><span>- {money(q.subtotal - q.total, q.currency)}</span></div>
              </>
            )}
            <div className="flex justify-between text-lg font-semibold"><span>Total</span><span>{money(q.total, q.currency)}</span></div>
          </div>
          {q.expires_at && open && <p className="mt-3 text-xs text-slate-400">Valid until {new Date(q.expires_at).toLocaleDateString()}</p>}
        </div>

        {done && (
          <div className={`mt-4 rounded-2xl p-4 text-sm ring-1 ${done.cls}`}>
            <p className="font-semibold">{done.title}</p>
            <p className="mt-1">{done.text}</p>
            {q.customer_note && <p className="mt-2 italic">Your note: {q.customer_note}</p>}
          </div>
        )}

        {open && (
          <div className="mt-4">
            {mode === null ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <button onClick={() => setMode('accept')} className="rounded-xl bg-indigo-600 py-3 text-[15px] font-medium text-white hover:bg-indigo-700">Accept</button>
                <button onClick={() => setMode('changes')} className="rounded-xl border border-slate-300 bg-white py-3 text-[15px] hover:bg-slate-50">Ask for changes</button>
                <button onClick={() => setMode('decline')} className="rounded-xl border border-slate-300 bg-white py-3 text-[15px] text-slate-600 hover:bg-slate-50">Decline</button>
              </div>
            ) : (
              <div className="rounded-2xl bg-white p-4 ring-1 ring-slate-200">
                <label className="mb-1 block text-sm font-medium">
                  {mode === 'changes' ? 'What would you like changed?' : mode === 'accept' ? 'Anything we should know? (optional)' : 'Reason (optional)'}
                </label>
                <textarea
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-[15px] outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
                  rows={3}
                  maxLength={1000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
                {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
                <div className="mt-3 flex gap-2">
                  <button
                    disabled={busy || (mode === 'changes' && !note.trim())}
                    onClick={() => void send(mode)}
                    className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
                  >
                    {busy ? 'Sending...' : mode === 'accept' ? 'Confirm: accept quote' : mode === 'decline' ? 'Confirm: decline quote' : 'Send request'}
                  </button>
                  <button disabled={busy} onClick={() => { setMode(null); setError('') }} className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm hover:bg-slate-100">Back</button>
                </div>
              </div>
            )}
            {error && mode === null && <p className="mt-2 text-sm text-red-600">{error}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
