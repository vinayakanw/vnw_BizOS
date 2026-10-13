import { useEffect, useState, type FormEvent } from 'react'
import { api, type AskResult, type Overview, type Report } from '../lib/api'
import { money, ui } from '../lib/ui'

const EXAMPLES = [
  'How is my pipeline doing?',
  'Which leads should I call first?',
  'Which leads have gone quiet this week?',
  'How many leads did I get this month?',
  'How many discounts did I approve or reject?',
]

const MONEY_COLS = ['potential_value', 'value_before_discount']

function fmt(col: string, v: string | number | boolean) {
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'number' && MONEY_COLS.includes(col)) return money(v, 'INR')
  return String(v)
}

function Table({ r }: { r: Report }) {
  return (
    <div className={`${ui.card} overflow-x-auto p-0`}>
      <p className="px-4 pt-3 text-xs font-medium uppercase text-slate-500">
        {r.title}{r.window_days ? ` (${r.window_days} days)` : ''}
      </p>
      <div className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-2 text-sm">
        {Object.entries(r.facts).filter(([k]) => k !== 'currency').map(([k, v]) => (
          <span key={k} className="text-slate-600">
            {k.replace(/_/g, ' ')}: <span className="font-semibold text-slate-900">{typeof v === 'number' && /value/.test(k) ? money(v, 'INR') : String(v)}</span>
          </span>
        ))}
      </div>
      {r.rows.length > 0 ? (
        <table className="w-full text-left text-sm">
          <thead className="border-y border-slate-200 text-xs uppercase text-slate-500">
            <tr>{r.columns.map((c) => <th key={c} className="px-4 py-2">{c.replace(/_/g, ' ')}</th>)}</tr>
          </thead>
          <tbody>
            {r.rows.slice(0, 20).map((row, i) => (
              <tr key={i} className="border-b border-slate-100 last:border-0">
                {row.map((v, j) => <td key={j} className="px-4 py-2">{fmt(r.columns[j], v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="px-4 pb-4 text-sm text-slate-500">No data yet.</p>
      )}
    </div>
  )
}

function Bars({ r }: { r: Report }) {
  const max = Math.max(1, ...r.rows.map((x) => Number(x[1])))
  return (
    <div className={ui.card}>
      <p className="text-xs font-medium uppercase text-slate-500">New leads, last 14 days</p>
      <div className="mt-3 flex h-28 items-end gap-1">
        {r.rows.map((x) => (
          <div key={String(x[0])} className="flex flex-1 flex-col items-center justify-end" title={`${x[0]}: ${x[1]}`}>
            <span className="text-[10px] text-slate-500">{Number(x[1]) > 0 ? String(x[1]) : ''}</span>
            <div className="w-full rounded-t bg-indigo-500" style={{ height: `${(Number(x[1]) / max) * 80}%`, minHeight: Number(x[1]) > 0 ? 4 : 1, opacity: Number(x[1]) > 0 ? 1 : 0.25 }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-slate-400">
        <span>{String(r.rows[0]?.[0] ?? '')}</span>
        <span>{String(r.rows[r.rows.length - 1]?.[0] ?? '')}</span>
      </div>
    </div>
  )
}

export default function Analytics() {
  const [ov, setOv] = useState<Overview | null>(null)
  const [q, setQ] = useState('')
  const [res, setRes] = useState<AskResult | null>(null)
  const [asked, setAsked] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api<Overview>('/agents/analytics/overview').then(setOv).catch((e: Error) => setError(e.message))
  }, [])

  const ask = async (question: string, e?: FormEvent) => {
    e?.preventDefault()
    if (question.trim().length < 3 || busy) return
    setBusy(true)
    setError('')
    setAsked(question)
    try {
      setRes(await api<AskResult>('/agents/analytics/ask', { method: 'POST', body: JSON.stringify({ question }) }))
    } catch (err) {
      setRes(null)
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const f = ov?.pipeline.facts
  const tiles = [
    { label: 'Open pipeline', value: f ? money(Number(f.open_pipeline_value), 'INR') : '-' },
    { label: 'Won', value: f ? money(Number(f.won_value), 'INR') : '-' },
    { label: 'Win rate', value: f ? `${f.win_rate_pct}%` : '-' },
    { label: 'Quiet leads (3+ days)', value: ov ? String(ov.stale.facts.quiet_leads) : '-' },
    { label: 'Open tasks', value: ov ? `${ov.tasks.facts.open}${Number(ov.tasks.facts.overdue) ? ` (${ov.tasks.facts.overdue} overdue)` : ''}` : '-' },
  ]

  return (
    <div>
      <h1 className="text-2xl font-semibold">Reports</h1>
      <p className="mt-1 text-sm text-slate-500">Your numbers, live. Ask a question in plain words and the answer comes only from your own data, with the table shown so you can check it.</p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {tiles.map((t) => (
          <div key={t.label} className={ui.card}>
            <p className="text-sm text-slate-500">{t.label}</p>
            <p className="mt-1 text-xl font-semibold">{t.value}</p>
          </div>
        ))}
      </div>
      {ov && <div className="mt-4"><Bars r={ov.leads_over_time} /></div>}

      <h2 className="mt-8 text-lg font-semibold">Ask a question</h2>
      <form onSubmit={(e) => void ask(q, e)} className="mt-2 flex gap-2">
        <input className={ui.input} placeholder="e.g. Which leads should I call first?" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} />
        <button className={ui.btn} disabled={busy || q.trim().length < 3}>{busy ? 'Working...' : 'Ask'}</button>
      </form>
      <div className="mt-2 flex flex-wrap gap-2">
        {EXAMPLES.map((x) => (
          <button key={x} className="rounded-full border border-slate-300 px-3 py-1 text-xs hover:bg-slate-50" onClick={() => { setQ(x); void ask(x) }}>{x}</button>
        ))}
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {res && (
        <div className="mt-4 space-y-3">
          <div className={ui.card}>
            <p className="text-xs uppercase tracking-wide text-slate-400">{asked}</p>
            <p className="mt-2 whitespace-pre-wrap">{res.answer}</p>
          </div>
          {res.results.length > 0 && <p className="text-xs font-medium uppercase text-slate-500">Data behind this answer</p>}
          {res.results.map((r, i) => <Table key={i} r={r} />)}
        </div>
      )}
    </div>
  )
}
