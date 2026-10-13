import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type InboxDetail as Detail, type Lead } from '../lib/api'
import AuthImage from '../components/AuthImage'
import { emailStatusText, inboxStateLabel } from '../lib/leadStatus'
import { money, ui } from '../lib/ui'
import { statusColor } from '../lib/leadStatus'

export default function InboxDetail() {
  const { id } = useParams()
  const [d, setD] = useState<Detail | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [emailStatus, setEmailStatus] = useState<string | null>(null) // from the last reply; polling would otherwise wipe it
  const [lead, setLead] = useState<Lead | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    api<Detail>(`/inbox/${id}`)
      .then((x) => {
        setD(x)
        if (x.item.lead_id) api<{ lead: Lead }>(`/leads/${x.item.lead_id}`).then((r) => setLead(r.lead)).catch(() => {})
      })
      .catch((e: Error) => setError(e.message))
  }, [id])

  useEffect(() => {
    load()
    const t = setInterval(load, 5000) // customers may be writing right now
    return () => clearInterval(t)
  }, [load])

  const count = d?.messages.length ?? 0
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [count])

  const call = async (path: string, body?: unknown) => {
    setBusy(true)
    setError('')
    try {
      const r = await api<Detail>(`/inbox/${id}/${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
      setD(r)
      setEmailStatus(path === 'reply' ? (r.email_status ?? null) : null)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
      return false
    } finally {
      setBusy(false)
    }
  }

  const send = async (e: FormEvent) => {
    e.preventDefault()
    const body = text.trim()
    if (!body) return
    if (await call('reply', { body })) setText('')
  }

  if (error && !d) return <div><Link to="/inbox" className="text-sm text-slate-500 hover:underline">Back to inbox</Link><p className="mt-3 text-sm text-red-600">{error}</p></div>
  if (!d) return <p className="text-sm text-slate-500">Loading...</p>
  const it = d.item
  const st = inboxStateLabel[it.state]

  return (
    <div>
      <Link to="/inbox" className="text-sm text-slate-500 hover:underline">Back to inbox</Link>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{it.customer_name ?? it.customer_email ?? 'Customer'}</h1>
        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">{it.mode}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${st.cls}`}>{st.label}</span>
      </div>
      <p className="mt-1 text-sm text-slate-500">{it.customer_email}</p>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {emailStatus && emailStatusText[emailStatus] && <p className={`mt-2 text-sm ${emailStatusText[emailStatus].cls}`}>{emailStatusText[emailStatus].text}</p>}

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <div className={`${ui.card} flex h-[34rem] flex-col lg:col-span-3`}>
          <div className="flex-1 space-y-3 overflow-y-auto pr-1">
            {d.messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === 'customer' ? 'justify-start' : 'justify-end'}`}>
                <div className="max-w-[85%]">
                  <p className={`px-1 text-xs ${m.role === 'customer' ? 'text-slate-400' : 'text-right text-slate-400'}`}>
                    {m.role === 'customer' ? 'Customer' : m.role === 'human' ? 'You / team' : 'AI'}
                  </p>
                  <p
                    className={`whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
                      m.role === 'customer' ? 'bg-slate-100' : m.role === 'human' ? 'bg-emerald-600 text-white' : 'bg-indigo-50 text-slate-800 ring-1 ring-indigo-100'
                    }`}
                  >
                    {m.attachment_id && <AuthImage path={`/inbox/attachments/${m.attachment_id}`} className="mb-1 max-h-64 rounded-xl" />}
                    {m.content}
                  </p>
                </div>
              </div>
            ))}
            <div ref={bottom} />
          </div>
          {d.can_reply ? (
            <form onSubmit={send} className="mt-3 flex gap-2">
              <input className={ui.input} placeholder="Reply to the customer" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
              <button disabled={busy || !text.trim()} className={ui.btn}>Send</button>
            </form>
          ) : (
            <p className="mt-3 text-sm text-slate-500">This is a test chat from the dashboard, so there is no customer to reply to.</p>
          )}
        </div>

        <div className="space-y-4 lg:col-span-2">
          {lead && (
            <div className={ui.card}>
              <div className="flex items-start justify-between">
                <p className="text-xs font-medium uppercase text-slate-500">Live read on this customer</p>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor[lead.status] ?? 'bg-slate-100 text-slate-700'}`}>{lead.status}</span>
              </div>
              <div className="mt-2 flex items-end gap-2">
                <p className="font-display text-4xl font-bold">{lead.score}</p>
                <p className="pb-1 text-sm text-slate-400">/ 100 buying score</p>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-indigo-500" style={{ width: `${lead.score}%` }} /></div>
              <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                <dt className="text-slate-500">Wants</dt><dd className="font-medium">{lead.requirement ?? '-'}</dd>
                <dt className="text-slate-500">Quantity</dt><dd className="font-medium">{lead.quantity ?? '-'}</dd>
                <dt className="text-slate-500">Budget each</dt><dd className="font-medium">{lead.budget_per_unit ? money(lead.budget_per_unit, lead.currency ?? 'INR') : '-'}</dd>
                <dt className="text-slate-500">When</dt><dd className="font-medium">{lead.timeline ?? '-'}</dd>
                <dt className="text-slate-500">Intent</dt><dd className="font-medium">{lead.intent}</dd>
              </dl>
              {lead.score_reasons.length > 0 && <ul className="mt-3 list-disc space-y-0.5 pl-5 text-xs text-slate-600">{lead.score_reasons.slice(0, 4).map((r) => <li key={r}>{r}</li>)}</ul>}
              {lead.next_action && <p className="mt-3 rounded-xl bg-marigold/15 p-2.5 text-sm font-medium">Next: {lead.next_action}</p>}
            </div>
          )}
          {d.escalation_reason && (
            <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-semibold">Why it needs a person</p>
              <p className="mt-1">{d.escalation_reason}</p>
            </div>
          )}
          {d.can_reply && (
            <div className={ui.card}>
              <p className="text-xs font-medium uppercase text-slate-500">Who is answering</p>
              <p className="mt-2 text-sm text-slate-600">
                {it.state === 'human'
                  ? 'You are handling this chat. The AI will not answer until you hand it back.'
                  : 'The AI is answering. Sending a reply takes the chat over.'}
              </p>
              {(it.state === 'human' || it.state === 'needs_human') && (
                <button className={`${ui.btnGhost} mt-3`} disabled={busy} onClick={() => call('handback')}>Hand back to the AI</button>
              )}
            </div>
          )}
          <div className={ui.card}>
            <p className="text-xs font-medium uppercase text-slate-500">Linked records</p>
            <ul className="mt-2 space-y-1 text-sm">
              {it.lead_id && <li><Link className="text-indigo-700 hover:underline" to={`/leads/${it.lead_id}`}>Open the lead</Link></li>}
              {d.ticket_id && <li><Link className="text-indigo-700 hover:underline" to={`/tickets/${d.ticket_id}`}>Open ticket {it.ticket_number}</Link></li>}
              {!it.lead_id && !d.ticket_id && <li className="text-slate-500">None yet</li>}
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
