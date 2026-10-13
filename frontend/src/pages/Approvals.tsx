import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type ToolCall } from '../lib/api'
import { actionColor, toolLabel } from '../lib/leadStatus'
import { ui } from '../lib/ui'

type Rules = { auto_discount_max_pct: number; auto_discount_min_qty: number; quote_approval_above: number | null; always_approve_tools: string[] }
const TOOLS = ['create_quote', 'create_followup_task', 'draft_email']

function RulesCard() {
  const [r, setR] = useState<Rules | null>(null)
  const [limit, setLimit] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    api<Rules>('/approvals/rules').then((x) => { setR(x); setLimit(x.quote_approval_above == null ? '' : String(x.quote_approval_above)) }).catch((e: Error) => setError(e.message))
  }, [])

  if (!r) return null
  const save = async () => {
    setError('')
    setMsg('')
    try {
      const body = { ...r, quote_approval_above: limit.trim() === '' ? null : Number(limit) }
      setR(await api<Rules>('/approvals/rules', { method: 'PUT', body: JSON.stringify(body) }))
      setMsg('Saved')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    }
  }

  return (
    <details className={`${ui.card} mt-4`}>
      <summary className="cursor-pointer font-medium">Approval rules</summary>
      <p className="mt-2 text-sm text-slate-500">The agent and your workflows follow these. Anything outside them waits here for you.</p>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div>
          <label className={ui.label}>Discount allowed without approval (%)</label>
          <input className={ui.input} inputMode="decimal" value={r.auto_discount_max_pct} onChange={(e) => setR({ ...r, auto_discount_max_pct: Number(e.target.value) || 0 })} />
        </div>
        <div>
          <label className={ui.label}>...only on orders of at least (units)</label>
          <input className={ui.input} inputMode="numeric" value={r.auto_discount_min_qty} onChange={(e) => setR({ ...r, auto_discount_min_qty: Number(e.target.value) || 1 })} />
        </div>
        <div>
          <label className={ui.label}>Quotes above this total need approval</label>
          <input className={ui.input} inputMode="numeric" placeholder="No limit" value={limit} onChange={(e) => setLimit(e.target.value)} />
        </div>
      </div>
      <div className="mt-3">
        <label className={ui.label}>Always ask me before the agent does these</label>
        <div className="flex flex-wrap gap-4 text-sm">
          {TOOLS.map((t) => (
            <label key={t} className="flex items-center gap-2">
              <input type="checkbox" checked={r.always_approve_tools.includes(t)} onChange={(e) => setR({ ...r, always_approve_tools: e.target.checked ? [...r.always_approve_tools, t] : r.always_approve_tools.filter((x) => x !== t) })} />
              {toolLabel[t]}
            </label>
          ))}
        </div>
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <div className="mt-3 flex items-center gap-3">
        <button className={ui.btn} onClick={() => void save()}>Save rules</button>
        {msg && <span className="text-sm text-green-700">{msg}</span>}
      </div>
    </details>
  )
}

function describe(c: ToolCall): string {
  const a = c.args as Record<string, string | number>
  if (c.tool === 'create_quote') return `${a.quantity} x ${a.product_name}${a.discount_pct ? ` at ${a.discount_pct}% discount` : ''}`
  if (c.tool === 'create_followup_task') return String(a.title ?? '')
  if (c.tool === 'draft_email') return String(a.subject ?? '')
  return JSON.stringify(a)
}

export default function Approvals() {
  const [pending, setPending] = useState<ToolCall[] | null>(null)
  const [history, setHistory] = useState<ToolCall[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api<ToolCall[]>('/approvals').then(setPending).catch((e: Error) => setError(e.message))
    api<ToolCall[]>('/tool-calls?limit=30').then(setHistory).catch(() => undefined)
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const decide = async (id: string, verb: 'approve' | 'reject') => {
    setBusy(id)
    setError('')
    try {
      await api(`/approvals/${id}/${verb}`, { method: 'POST', body: verb === 'reject' ? JSON.stringify({ reason }) : undefined })
      setRejecting(null)
      setReason('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setBusy(null)
      load()
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Needs your OK</h1>
      <p className="mt-1 text-sm text-slate-500">Things the AI wants to do but will not without you, like a big discount. Nothing happens until you say yes.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      <RulesCard />

      <div className="mt-4 space-y-3">
        {pending?.map((c) => (
          <div key={c.id} className={`${ui.card} border-l-4 border-amber-400`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-slate-400">{toolLabel[c.tool] ?? c.tool}</p>
                <p className="mt-1 font-medium">{describe(c)}</p>
                <p className="mt-1 text-sm text-amber-800">{c.approval_reason}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {c.lead_id ? <Link to={`/leads/${c.lead_id}`} className="text-indigo-700 hover:underline">{c.lead_name ?? 'Lead'}</Link> : 'No lead'}
                  {' · '}{new Date(c.created_at).toLocaleString()}
                </p>
              </div>
              <div className="flex gap-2">
                <button className={ui.btn} disabled={busy === c.id} onClick={() => void decide(c.id, 'approve')}>Approve</button>
                <button className={ui.btnDanger} disabled={busy === c.id} onClick={() => setRejecting(rejecting === c.id ? null : c.id)}>Reject</button>
              </div>
            </div>
            {rejecting === c.id && (
              <div className="mt-3 flex gap-2">
                <input className={ui.input} placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
                <button className={ui.btnDanger} disabled={busy === c.id} onClick={() => void decide(c.id, 'reject')}>Confirm reject</button>
              </div>
            )}
          </div>
        ))}
        {pending?.length === 0 && <p className="py-8 text-center text-sm text-slate-500">Nothing waiting for approval.</p>}
      </div>

      <h2 className="mt-8 text-lg font-semibold">Recent actions</h2>
      <div className={`${ui.card} mt-3 divide-y divide-slate-100 p-0`}>
        {history.map((c) => (
          <div key={c.id} className="flex items-start justify-between gap-3 px-4 py-3 text-sm">
            <div>
              <p className="font-medium">{toolLabel[c.tool] ?? c.tool}: <span className="font-normal text-slate-600">{c.error ?? c.summary}</span></p>
              <p className="text-xs text-slate-400">
                {new Date(c.created_at).toLocaleString()}
                {c.decided_by && ` · ${c.status === 'rejected' ? 'rejected' : 'approved'} by ${c.decided_by}`}
              </p>
            </div>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${actionColor[c.status]}`}>{c.status.replace('_', ' ')}</span>
          </div>
        ))}
        {history.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-500">No actions yet.</p>}
      </div>
    </div>
  )
}
