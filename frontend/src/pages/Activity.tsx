import { useEffect, useState } from 'react'
import { api, type Run } from '../lib/api'
import { ui } from '../lib/ui'

const badge: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  escalated: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-700',
  running: 'bg-slate-100 text-slate-700',
}

export default function Activity() {
  const [runs, setRuns] = useState<Run[] | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = () => api<Run[]>('/agents/runs').then(setRuns).catch((e: Error) => setError(e.message))
  useEffect(() => {
    void load()
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">What the AI did</h1>
        <button className={ui.btnGhost} onClick={() => void load()}>Refresh</button>
      </div>
      <p className="mt-1 text-sm text-slate-500">Every agent run, step by step. Click a run to see what it did and why.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 space-y-3">
        {runs?.map((r) => (
          <div key={r.id} className={ui.card}>
            <button className="flex w-full items-start justify-between gap-4 text-left" onClick={() => setOpen(open === r.id ? null : r.id)}>
              <div>
                <p className="text-sm font-medium">{r.summary ?? r.error ?? 'Running...'}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {new Date(r.created_at).toLocaleString()}
                  {r.duration_ms != null && ` · ${(r.duration_ms / 1000).toFixed(1)}s`}
                </p>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${badge[r.status]}`}>{r.status}</span>
            </button>
            {open === r.id && (
              <ol className="mt-3 space-y-1.5 border-t border-slate-100 pt-3 text-sm">
                {r.steps.map((s, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="w-20 shrink-0 text-xs text-slate-400">{new Date(s.t).toLocaleTimeString()}</span>
                    <span>
                      <span className="font-medium">{s.step}</span>
                      {s.detail && <span className="text-slate-500">: {s.detail}</span>}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </div>
        ))}
        {runs?.length === 0 && <p className="py-8 text-center text-sm text-slate-500">No agent runs yet.</p>}
      </div>
    </div>
  )
}
