import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Lead, type Pipeline } from '../lib/api'
import { STATUSES, statusColor } from '../lib/leadStatus'
import { money, ui } from '../lib/ui'

export default function Leads() {
  const [items, setItems] = useState<Lead[] | null>(null)
  const [summary, setSummary] = useState<Pipeline | null>(null)
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (q.trim()) params.set('q', q.trim())
    api<Lead[]>(`/leads?${params.toString()}`).then(setItems).catch((e: Error) => setError(e.message))
    api<Pipeline>('/leads/summary').then(setSummary).catch(() => setSummary(null))
  }, [status, q])

  useEffect(() => {
    const t = setTimeout(load, 250)
    return () => clearTimeout(t)
  }, [load])

  const tiles = [
    { label: 'Open pipeline', value: summary ? money(summary.open_value, 'INR') : '-' },
    { label: 'Won', value: summary ? money(summary.won_value, 'INR') : '-' },
    { label: 'Hot leads', value: summary?.counts.HOT ?? '-' },
    { label: 'Win rate', value: summary ? `${Math.round(summary.conversion_rate * 100)}%` : '-' },
  ]

  return (
    <div>
      <h1 className="text-2xl font-semibold">Leads</h1>
      <p className="mt-1 text-sm text-slate-500">People who showed interest in buying. The AI scores them, hot ones first. Open one to see the chat and follow up.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className={ui.card}>
            <p className="text-sm text-slate-500">{t.label}</p>
            <p className="mt-1 text-2xl font-semibold">{t.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button className={`${status === '' ? ui.btn : ui.btnGhost}`} onClick={() => setStatus('')}>All</button>
        {STATUSES.map((s) => (
          <button key={s} className={status === s ? ui.btn : ui.btnGhost} onClick={() => setStatus(s)}>
            {s} {summary ? `(${summary.counts[s] ?? 0})` : ''}
          </button>
        ))}
        <input className={`${ui.input} ml-auto max-w-xs`} placeholder="Search name, company, email, need" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <div className={`${ui.card} mt-4 overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Requirement</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Potential value</th>
              <th className="px-4 py-3">Next action</th>
            </tr>
          </thead>
          <tbody>
            {items?.map((l) => (
              <tr key={l.id} className="border-b border-slate-100 align-top last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link to={`/leads/${l.id}`} className="font-medium text-indigo-700 hover:underline">{l.name ?? l.email ?? 'Unknown customer'}</Link>
                  <p className="text-xs text-slate-500">{l.company ?? (l.name ? l.email : '') ?? ''}</p>
                </td>
                <td className="px-4 py-3">{l.requirement ?? '-'}</td>
                <td className="px-4 py-3 font-semibold">{l.score}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor[l.status]}`}>{l.status}</span>
                </td>
                <td className="px-4 py-3">{l.potential_value ? money(l.potential_value, l.currency ?? 'INR') : '-'}</td>
                <td className="px-4 py-3 text-slate-600">{l.next_action ?? '-'}</td>
              </tr>
            ))}
            {items?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">No leads match. Chat with the Sales Agent to create one.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
