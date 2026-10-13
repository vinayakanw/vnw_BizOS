import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type Lead, type LeadDetail as Detail } from '../lib/api'
import { useAuth } from '../lib/auth'
import { quoteStatusLabel } from '../lib/leadStatus'
import { actionColor, statusColor, toolLabel } from '../lib/leadStatus'
import { money, ui } from '../lib/ui'

export default function LeadDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [task, setTask] = useState('')
  const [edit, setEdit] = useState({ name: '', company: '', email: '', phone: '' })
  const [saved, setSaved] = useState(false)
  const [sending, setSending] = useState('')
  const [quoteMsg, setQuoteMsg] = useState('')
  const { me } = useAuth()

  const load = useCallback(() => {
    api<Detail>(`/leads/${id}`)
      .then((x) => {
        setD(x)
        setEdit({ name: x.lead.name ?? '', company: x.lead.company ?? '', email: x.lead.email ?? '', phone: x.lead.phone ?? '' })
      })
      .catch((e: Error) => setError(e.message))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const patch = async (body: Record<string, string>) => {
    setError('')
    try {
      await api<Lead>(`/leads/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
      load()
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Update failed')
      return false
    }
  }

  const saveContact = async () => {
    if (await patch(edit)) {
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    }
  }

  const removeLead = async () => {
    if (!confirm('Delete this lead with its conversation, notes, tasks and quotes? This cannot be undone.')) return
    try {
      await api(`/leads/${id}`, { method: 'DELETE' })
      navigate('/leads')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete')
    }
  }

  const deliverQuote = async (qid: string) => {
    setQuoteMsg('')
    try {
      const r = await api<{ chat: boolean; email: string }>(`/quotes/${qid}/deliver`, { method: 'POST' })
      const mail: Record<string, string> = {
        sent: 'and emailed it',
        skipped_online: 'the customer is on the page, no email needed',
        no_email_setup: 'email is not connected, so no email was sent',
        no_customer_email: 'there is no email for this customer',
        failed: 'the email failed, check Integrations',
      }
      setQuoteMsg(`${r.chat ? 'Link posted in the customer chat' : 'No chat to post in'}, ${mail[r.email] ?? r.email}.`)
      load()
    } catch (e) {
      setQuoteMsg(e instanceof Error ? e.message : 'Could not send the quote')
    }
  }

  const copyQuoteLink = async (token: string) => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/quote/${token}`)
      setQuoteMsg('Quote link copied.')
    } catch {
      setQuoteMsg(`${window.location.origin}/quote/${token}`)
    }
  }

  const addNote = async () => {
    if (!note.trim()) return
    try {
      await api(`/leads/${id}/notes`, { method: 'POST', body: JSON.stringify({ body: note }) })
      setNote('')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add note')
    }
  }

  const addTask = async () => {
    if (!task.trim()) return
    try {
      await api(`/leads/${id}/tasks`, { method: 'POST', body: JSON.stringify({ title: task, due_in_days: 1 }) })
      setTask('')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add task')
    }
  }

  const toggleTask = async (tid: string, done: boolean) => {
    await api(`/leads/${id}/tasks/${tid}`, { method: 'PATCH', body: JSON.stringify({ status: done ? 'open' : 'done' }) }).catch((e: Error) => setError(e.message))
    load()
  }

  const delNote = async (nid: string) => {
    await api(`/leads/${id}/notes/${nid}`, { method: 'DELETE' }).catch((e: Error) => setError(e.message))
    load()
  }

  const sendDraft = async (id: string, to: string) => {
    if (!window.confirm(`Send this email to ${to} now? This cannot be undone.`)) return
    setSending(id)
    setError('')
    try {
      const r = await api<{ status: string; error: string | null }>(`/tool-calls/${id}/send`, { method: 'POST' })
      if (r.status === 'failed') setError(r.error ?? 'Could not send')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send')
    } finally {
      setSending('')
    }
  }

  if (error && !d) return <div><Link to="/leads" className="text-sm text-indigo-700">Back to leads</Link><p className="mt-3 text-sm text-red-600">{error}</p></div>
  if (!d) return <p className="text-sm text-slate-500">Loading...</p>
  const l = d.lead
  const closed = l.status === 'CONVERTED' || l.status === 'LOST'

  return (
    <div>
      <Link to="/leads" className="text-sm text-indigo-700 hover:underline">Back to leads</Link>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold">{l.name ?? l.email ?? 'Unknown customer'}</h1>
          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor[l.status]}`}>{l.status}</span>
          <span className="text-sm text-slate-500">Score {l.score}/100</span>
        </div>
        <div className="flex gap-2">
          {closed ? (
            <button className={ui.btnGhost} onClick={() => void patch({ status: 'OPEN' })}>Reopen</button>
          ) : (
            <>
              <button className={ui.btn} onClick={() => void patch({ status: 'CONVERTED' })}>Mark won</button>
              <button className={ui.btnDanger} onClick={() => void patch({ status: 'LOST' })}>Mark lost</button>
            </>
          )}
          <button className={ui.btnGhost} onClick={() => void removeLead()}>Delete</button>
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {d.conversations.map((c) => (
            <div key={c.id} className={ui.card}>
              <div className="mb-3 flex items-center justify-between">
                <p className="text-xs uppercase tracking-wide text-slate-400">Conversation · {new Date(c.created_at).toLocaleString()}</p>
                <span className="flex items-center gap-3">
                  {c.escalated && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Needs human</span>}
                  <Link to={`/inbox/${c.id}`} className="text-xs text-indigo-700 hover:underline">Open in Inbox</Link>
                </span>
              </div>
              {c.escalation_reason && <p className="mb-3 rounded-lg bg-amber-50 p-2 text-sm text-amber-900">{c.escalation_reason}</p>}
              <div className="space-y-2">
                {c.messages.map((m) => (
                  <div key={m.id} className={`flex ${m.role === 'customer' ? 'justify-end' : ''}`}>
                    <p className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${m.role === 'customer' ? 'bg-indigo-600 text-white' : m.role === 'human' ? 'bg-emerald-100' : 'bg-slate-100'}`}>{m.content}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {d.quotes.length > 0 && (
            <div className={ui.card}>
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-400">Quotes</p>
              {quoteMsg && <p className="mb-2 text-sm text-slate-600">{quoteMsg}</p>}
              <div className="space-y-3">
                {d.quotes.map((q) => (
                  <div key={q.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                    <div className="flex justify-between font-medium"><span>{q.number}</span><span>{money(q.total, q.currency)}</span></div>
                    {q.items.map((it, i) => (
                      <p key={i} className="mt-1 text-slate-600">{it.quantity} x {it.product} at {money(it.unit_price, q.currency)}</p>
                    ))}
                    {q.discount_pct > 0 && <p className="mt-1 text-slate-600">Discount {q.discount_pct}% on {money(q.subtotal, q.currency)}</p>}
                    <p className="mt-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${quoteStatusLabel[q.status]?.cls ?? ''}`}>{quoteStatusLabel[q.status]?.label ?? q.status}</span>
                    </p>
                    {q.customer_note && <p className="mt-1 rounded-lg bg-slate-50 p-2 text-slate-700">Customer note: {q.customer_note}</p>}
                    {!q.customer_response && (me?.role === 'owner' || me?.role === 'admin') && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button className={ui.btnGhost} onClick={() => void deliverQuote(q.id)}>{q.status === 'draft' ? 'Send to customer' : 'Send again'}</button>
                        {q.public_token && q.status !== 'draft' && <button className={ui.btnGhost} onClick={() => void copyQuoteLink(q.public_token as string)}>Copy link</button>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {d.tool_calls.length > 0 && (
            <div className={ui.card}>
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-400">Agent actions</p>
              <ul className="space-y-2 text-sm">
                {d.tool_calls.map((c) => (
                  <li key={c.id}>
                    <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${actionColor[c.status]}`}>{c.status.replace('_', ' ')}</span>
                    <span className="font-medium">{toolLabel[c.tool] ?? c.tool}</span>
                    <p className="mt-0.5 text-slate-600">{c.error ?? c.summary}</p>
                    {c.tool === 'draft_email' && c.result && (
                      <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-slate-50 p-2 font-sans text-xs text-slate-700">{`To: ${String(c.result.to ?? '(no email yet)')}\nSubject: ${String(c.result.subject)}\n\n${String(c.result.body)}`}</pre>
                    )}
                    {c.tool === 'send_email' && c.status === 'executed' && <p className="mt-0.5 text-xs text-green-700">Sent</p>}
                    {c.tool === 'draft_email' && c.status === 'executed' && Boolean(c.result?.to) && (me?.role === 'owner' || me?.role === 'admin') &&
                      !d.tool_calls.some((x) => x.tool === 'send_email' && x.status === 'executed' && x.args.subject === c.result?.subject && x.args.body === c.result?.body) && (
                        <button className={`${ui.btnGhost} mt-1`} disabled={sending === c.id} onClick={() => sendDraft(c.id, String(c.result?.to))}>
                          {sending === c.id ? 'Sending...' : 'Send this email'}
                        </button>
                      )}
                    {c.status === 'pending_approval' && <Link to="/approvals" className="text-xs text-indigo-700 hover:underline">Review in Approvals</Link>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {d.conversations.length === 0 && <div className={ui.card}><p className="text-sm text-slate-500">No conversation recorded.</p></div>}
        </div>

        <div className="space-y-4">
          <div className={ui.card}>
            <p className="text-xs uppercase tracking-wide text-slate-400">Deal</p>
            <p className="mt-2 text-sm">{l.requirement ?? 'No requirement captured yet'}</p>
            <dl className="mt-3 space-y-1 text-sm">
              <div className="flex justify-between"><dt className="text-slate-500">Quantity</dt><dd>{l.quantity ?? '-'}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Budget / unit</dt><dd>{l.budget_per_unit ? money(l.budget_per_unit, l.currency ?? 'INR') : '-'}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Potential value</dt><dd>{l.potential_value ? money(l.potential_value, l.currency ?? 'INR') : '-'}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Timeline</dt><dd>{l.timeline ?? '-'}</dd></div>
            </dl>
            {l.next_action && <p className="mt-3 rounded-lg bg-slate-50 p-2 text-sm font-medium">Next: {l.next_action}</p>}
          </div>

          <div className={ui.card}>
            <p className="text-xs uppercase tracking-wide text-slate-400">Contact</p>
            <div className="mt-2 space-y-2">
              {(['name', 'company', 'email', 'phone'] as const).map((f) => (
                <div key={f}>
                  <label className={ui.label}>{f[0].toUpperCase() + f.slice(1)}</label>
                  <input className={ui.input} value={edit[f]} onChange={(e) => setEdit({ ...edit, [f]: e.target.value })} />
                </div>
              ))}
              <button className={ui.btn} onClick={() => void saveContact()}>{saved ? 'Saved' : 'Save contact'}</button>
            </div>
          </div>

          <div className={ui.card}>
            <p className="text-xs uppercase tracking-wide text-slate-400">Tasks</p>
            <ul className="mt-2 space-y-1.5 text-sm">
              {d.tasks.map((t) => (
                <li key={t.id} className="flex items-start gap-2">
                  <input type="checkbox" className="mt-1" checked={t.status === 'done'} onChange={() => void toggleTask(t.id, t.status === 'done')} />
                  <span className={t.status === 'done' ? 'text-slate-400 line-through' : ''}>
                    {t.title}
                    <span className="block text-xs text-slate-400">{t.created_by}{t.due_at ? ` · due ${new Date(t.due_at).toLocaleDateString()}` : ''}</span>
                  </span>
                </li>
              ))}
            </ul>
            <div className="mt-2 flex gap-2">
              <input className={ui.input} placeholder="Add a task" value={task} onChange={(e) => setTask(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && void addTask()} />
              <button className={ui.btnGhost} disabled={!task.trim()} onClick={() => void addTask()}>Add</button>
            </div>
          </div>

          <div className={ui.card}>
            <p className="text-xs uppercase tracking-wide text-slate-400">Notes</p>
            <textarea className={`${ui.input} mt-2`} rows={3} placeholder="Called, wants a demo on Friday..." value={note} onChange={(e) => setNote(e.target.value)} />
            <button className={`${ui.btn} mt-2`} disabled={!note.trim()} onClick={() => void addNote()}>Add note</button>
            <ul className="mt-3 space-y-2">
              {d.notes.map((n) => (
                <li key={n.id} className="rounded-lg bg-slate-50 p-2 text-sm">
                  <p className="whitespace-pre-wrap">{n.body}</p>
                  <p className="mt-1 flex items-center justify-between text-xs text-slate-400">
                    <span>{n.author_name} · {new Date(n.created_at).toLocaleString()}</span>
                    <button className="text-red-500 hover:underline" onClick={() => void delNote(n.id)}>Delete</button>
                  </p>
                </li>
              ))}
            </ul>
          </div>

          <div className={ui.card}>
            <p className="text-xs uppercase tracking-wide text-slate-400">Why this score</p>
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">
              {l.score_reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
