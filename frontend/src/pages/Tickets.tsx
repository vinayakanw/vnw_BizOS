import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Ticket } from '../lib/api'
import { priorityColor, ticketStatusColor } from '../lib/leadStatus'
import { ui } from '../lib/ui'

const FILTERS = [
  { v: '', label: 'All' },
  { v: 'open', label: 'Open' },
  { v: 'in_progress', label: 'In progress' },
  { v: 'resolved', label: 'Resolved' },
]

export default function Tickets() {
  const [items, setItems] = useState<Ticket[] | null>(null)
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    const p = new URLSearchParams()
    if (status) p.set('status', status)
    if (q.trim()) p.set('q', q.trim())
    api<Ticket[]>(`/tickets?${p.toString()}`).then(setItems).catch((e: Error) => setError(e.message))
  }, [status, q])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  return (
    <div>
      <h1 className="text-2xl font-semibold">Tickets</h1>
      <p className="mt-1 text-sm text-slate-500">Problems the AI could not solve alone: returns, delivery, complaints. Open ones come first.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button key={f.v} className={status === f.v ? ui.btn : ui.btnGhost} onClick={() => setStatus(f.v)}>{f.label}</button>
        ))}
        <input className={`${ui.input} ml-auto max-w-xs`} placeholder="Search number, subject, customer, order" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className={`${ui.card} mt-4 overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Ticket</th>
              <th className="px-4 py-3">Subject</th>
              <th className="px-4 py-3">Customer</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {items === null && <tr><td className="px-4 py-6 text-slate-500" colSpan={6}>Loading...</td></tr>}
            {items?.length === 0 && <tr><td className="px-4 py-6 text-slate-500" colSpan={6}>No tickets. Try the Support Agent with an order status question.</td></tr>}
            {items?.map((t) => (
              <tr key={t.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium"><Link to={`/tickets/${t.id}`} className="text-indigo-700 hover:underline">{t.number}</Link></td>
                <td className="max-w-xs truncate px-4 py-3">{t.subject}</td>
                <td className="px-4 py-3 text-slate-600">{t.customer_name ?? t.email ?? '-'}</td>
                <td className="px-4 py-3 text-slate-600">{t.category.replace('_', ' ')}</td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${priorityColor[t.priority]}`}>{t.priority}</span></td>
                <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ticketStatusColor[t.status]}`}>{t.status.replace('_', ' ')}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
