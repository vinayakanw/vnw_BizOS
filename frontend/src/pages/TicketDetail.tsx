import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Ticket, type TicketDetail as Detail } from '../lib/api'
import { priorityColor, ticketStatusColor } from '../lib/leadStatus'
import { ui } from '../lib/ui'

const STATUS = ['open', 'in_progress', 'resolved'] as const
const PRIORITY = ['low', 'normal', 'high'] as const

export default function TicketDetail() {
  const { id } = useParams()
  const [d, setD] = useState<Detail | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api<Detail>(`/tickets/${id}`).then(setD).catch((e: Error) => setError(e.message))
  }, [id])
  useEffect(load, [load])

  const patch = async (body: Partial<Pick<Ticket, 'status' | 'priority'>>) => {
    setError('')
    try {
      const t = await api<Ticket>(`/tickets/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
      setD((x) => (x ? { ...x, ticket: t } : x))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update')
    }
  }

  if (error && !d) return <p className="text-sm text-red-600">{error}</p>
  if (!d) return <p className="text-sm text-slate-500">Loading...</p>
  const t = d.ticket

  return (
    <div>
      <Link to="/tickets" className="text-sm text-slate-500 hover:underline">Back to tickets</Link>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{t.number}</h1>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ticketStatusColor[t.status]}`}>{t.status.replace('_', ' ')}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${priorityColor[t.priority]}`}>{t.priority}</span>
      </div>
      <p className="mt-1 text-slate-700">{t.subject}</p>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <div className={`${ui.card} lg:col-span-3`}>
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase text-slate-500">Conversation</p>
            <Link to={`/inbox/${t.conversation_id}`} className="text-sm text-indigo-700 hover:underline">Open in Inbox to reply</Link>
          </div>
          <div className="mt-3 space-y-3">
            {d.conversation?.messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === 'customer' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${m.role === 'customer' ? 'bg-indigo-600 text-white' : m.role === 'human' ? 'bg-emerald-100' : 'bg-slate-100'}`}>{m.content}</div>
              </div>
            ))}
            {!d.conversation && <p className="text-sm text-slate-500">Conversation not found.</p>}
          </div>
        </div>

        <div className="space-y-4 lg:col-span-2">
          {t.escalation_reason && (
            <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-semibold">Why it was escalated</p>
              <p className="mt-1">{t.escalation_reason}</p>
            </div>
          )}
          <div className={ui.card}>
            <p className="text-xs font-medium uppercase text-slate-500">Manage</p>
            <p className="mt-3 text-xs text-slate-500">Status</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {STATUS.map((s) => (
                <button key={s} className={t.status === s ? ui.btn : ui.btnGhost} onClick={() => t.status !== s && void patch({ status: s })}>{s.replace('_', ' ')}</button>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-500">Priority</p>
            <div className="mt-1 flex flex-wrap gap-2">
              {PRIORITY.map((p) => (
                <button key={p} className={t.priority === p ? ui.btn : ui.btnGhost} onClick={() => t.priority !== p && void patch({ priority: p })}>{p}</button>
              ))}
            </div>
          </div>
          <div className={ui.card}>
            <p className="text-xs font-medium uppercase text-slate-500">Customer</p>
            <dl className="mt-2 space-y-1 text-sm text-slate-600">
              <div>Name: {t.customer_name ?? '-'}</div>
              <div>Email: {t.email ?? '-'}</div>
              <div>Phone: {t.phone ?? '-'}</div>
              <div>Order: {t.order_reference ?? '-'}</div>
              <div>Category: {t.category.replace('_', ' ')}</div>
            </dl>
          </div>
        </div>
      </div>
    </div>
  )
}
