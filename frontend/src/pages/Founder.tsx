import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Attention, type AttentionItem, type Briefing } from '../lib/api'
import { money, ui } from '../lib/ui'

const sevColor: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-800',
  low: 'bg-slate-100 text-slate-600',
}

function Item({ item, why }: { item: AttentionItem; why?: string }) {
  return (
    <li className="rounded-xl border border-slate-200 p-3 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${sevColor[item.severity]}`}>{item.severity}</span>
          <span className="font-medium">{item.title}</span>
        </div>
        <Link to={item.link} className="shrink-0 text-indigo-700 hover:underline">Open</Link>
      </div>
      <p className="mt-1 text-slate-600">{item.detail}</p>
      {why && <p className="mt-1 text-slate-800">Why now: {why}</p>}
    </li>
  )
}

export default function Founder() {
  const [attention, setAttention] = useState<Attention | null>(null)
  const [history, setHistory] = useState<Briefing[]>([])
  const [current, setCurrent] = useState<Briefing | null>(null)
  const [days, setDays] = useState(7)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [shared, setShared] = useState('')

  const load = useCallback(() => {
    api<Attention>('/agents/founder/attention').then(setAttention).catch((e: Error) => setError(e.message))
    api<Briefing[]>('/agents/founder/briefings')
      .then((h) => {
        setHistory(h)
        setCurrent((c) => c ?? h[0] ?? null)
      })
      .catch(() => undefined)
  }, [])
  useEffect(load, [load])

  const generate = async () => {
    setBusy(true)
    setError('')
    try {
      const b = await api<Briefing>('/agents/founder/briefing', { method: 'POST', body: JSON.stringify({ days }) })
      setCurrent(b)
      setHistory((h) => [b, ...h])
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not generate the briefing')
    } finally {
      setBusy(false)
    }
  }

  const share = async (id: string) => {
    setShared('')
    setError('')
    try {
      await api(`/agents/founder/briefings/${id}/share`, { method: 'POST' })
      setShared('Posted to Slack.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not share')
    }
  }

  const f = attention?.facts
  const tiles = f
    ? [
        { label: 'Open pipeline', value: money(Number(f.open_pipeline_value), 'INR') },
        { label: 'Hot leads', value: f.hot_leads },
        { label: 'Waiting approval', value: f.actions_waiting_approval },
        { label: 'Unresolved tickets', value: f.unresolved_tickets },
      ]
    : []

  return (
    <div>
      <h1 className="text-2xl font-semibold">Weekly briefing</h1>
      <p className="mt-1 text-sm text-slate-500">The few things that need you this week, picked from your real data. The AI only ranks them and says why they matter.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className={ui.card}>
            <p className="text-sm text-slate-500">{t.label}</p>
            <p className="mt-1 text-2xl font-semibold">{t.value}</p>
          </div>
        ))}
      </div>

      <div className={`${ui.card} mt-4`}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs font-medium uppercase text-slate-500">Briefing</p>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Last</span>
            <select className={`${ui.input} w-auto`} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[1, 7, 14, 30].map((d) => <option key={d} value={d}>{d} day{d > 1 ? 's' : ''}</option>)}
            </select>
            <button className={ui.btn} disabled={busy} onClick={generate}>{busy ? 'Writing...' : 'Generate briefing'}</button>
          </div>
        </div>
        {current ? (
          <div className="mt-3">
            <p className="text-lg font-semibold">{current.headline}</p>
            <p className="mt-1 text-sm text-slate-700">{current.summary}</p>
            <p className="mt-1 text-xs text-slate-400">
              {new Date(current.created_at).toLocaleString()}, last {current.period_days} day(s)
              {!current.ai_written && ' (AI was unavailable, built from the data only)'}
            </p>
            <div className="mt-2 flex items-center gap-2">
              <button className={ui.btnGhost} onClick={() => share(current.id)}>Share to Slack</button>
              {shared && <span className="text-sm text-green-700">{shared}</span>}
            </div>
            {current.priorities.length > 0 ? (
              <ol className="mt-3 space-y-2">
                {current.priorities.map((p) => <Item key={p.item.id} item={p.item} why={p.why} />)}
              </ol>
            ) : (
              <p className="mt-3 text-sm text-slate-500">No priorities in this briefing.</p>
            )}
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No briefing yet. Generate one, or check the live list below.</p>
        )}
      </div>

      <div className={`${ui.card} mt-4`}>
        <p className="text-xs font-medium uppercase text-slate-500">Needs attention right now (live, no AI)</p>
        {attention && attention.items.length === 0 && <p className="mt-2 text-sm text-slate-500">Nothing needs attention.</p>}
        <ul className="mt-3 space-y-2">
          {attention?.items.map((i) => <Item key={i.id} item={i} />)}
        </ul>
      </div>

      {history.length > 1 && (
        <div className={`${ui.card} mt-4`}>
          <p className="text-xs font-medium uppercase text-slate-500">Past briefings</p>
          <ul className="mt-2 space-y-1 text-sm">
            {history.map((h) => (
              <li key={h.id}>
                <button className="text-left text-indigo-700 hover:underline" onClick={() => setCurrent(h)}>
                  {new Date(h.created_at).toLocaleString()}
                </button>
                <span className="text-slate-600">: {h.headline}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
