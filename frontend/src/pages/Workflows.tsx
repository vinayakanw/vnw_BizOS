import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Lead, type Workflow, type WorkflowRun, type WorkflowStep } from '../lib/api'
import { actionColor, toolLabel } from '../lib/leadStatus'
import { ui } from '../lib/ui'

const TRIGGERS = [
  { v: 'lead.hot', l: 'A lead becomes HOT' },
  { v: 'lead.created', l: 'A new lead is captured' },
  { v: 'conversation.escalated', l: 'A conversation needs a human' },
  { v: 'lead.inactive', l: 'An open lead goes quiet' },
]
const FIELDS = ['score', 'quantity', 'potential_value', 'days_since_contact', 'status', 'intent', 'email', 'company']
const OPS: Record<string, string> = { gte: 'at least', lte: 'at most', eq: 'is', neq: 'is not', contains: 'contains', is_set: 'is filled in', not_set: 'is empty' }
const VARS = '{lead.name} {lead.company} {lead.quantity} {lead.score} {lead.potential_value} {lead.requirement} {lead.next_action} {lead.days_since_contact}'

const runColor: Record<string, string> = {
  completed: 'bg-green-100 text-green-800',
  partial: 'bg-amber-100 text-amber-800',
  failed: 'bg-red-100 text-red-700',
}

function stepText(s: WorkflowStep): string {
  const a = s.args
  const base =
    s.tool === 'create_followup_task' ? `Task: ${a.title}` : s.tool === 'draft_email' ? `Email draft: ${a.subject}` : `Quote: ${a.quantity} x ${a.product_name}${a.discount_pct ? ` (${a.discount_pct}% off)` : ''}`
  return s.condition ? `${base}  (only if ${s.condition.field} ${OPS[s.condition.op]})` : base
}

function Builder({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState('lead.hot')
  const [cField, setCField] = useState('')
  const [cOp, setCOp] = useState('gte')
  const [cVal, setCVal] = useState('')
  const [steps, setSteps] = useState<{ tool: 'create_followup_task' | 'draft_email'; a: string; b: string; days: string }[]>([
    { tool: 'create_followup_task', a: '', b: '', days: '1' },
  ])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const setStep = (i: number, patch: Partial<(typeof steps)[number]>) => setSteps(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))

  const save = async () => {
    setBusy(true)
    setError('')
    const needsValue = !['is_set', 'not_set'].includes(cOp)
    const num = ['score', 'quantity', 'potential_value'].includes(cField) && needsValue
    const body = {
      name,
      trigger,
      conditions: cField ? [{ field: cField, op: cOp, value: needsValue ? (num ? Number(cVal) : cVal) : null }] : [],
      steps: steps.map((s) =>
        s.tool === 'create_followup_task'
          ? { tool: s.tool, args: { title: s.a, due_in_days: Number(s.days) || 0 } }
          : { tool: s.tool, args: { subject: s.a, body: s.b } },
      ),
    }
    try {
      await api('/workflows', { method: 'POST', body: JSON.stringify(body) })
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`${ui.card} mt-4 space-y-4`}>
      <p className="font-medium">New workflow</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={ui.label}>Name</label>
          <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} placeholder="Call big orders today" />
        </div>
        <div>
          <label className={ui.label}>When</label>
          <select className={ui.input} value={trigger} onChange={(e) => setTrigger(e.target.value)}>
            {TRIGGERS.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label className={ui.label}>Only if (optional)</label>
        <div className="flex flex-wrap gap-2">
          <select className={`${ui.input} max-w-40`} value={cField} onChange={(e) => setCField(e.target.value)}>
            <option value="">Always</option>
            {FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          {cField && (
            <>
              <select className={`${ui.input} max-w-40`} value={cOp} onChange={(e) => setCOp(e.target.value)}>
                {Object.entries(OPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {!['is_set', 'not_set'].includes(cOp) && <input className={`${ui.input} max-w-40`} value={cVal} onChange={(e) => setCVal(e.target.value)} />}
            </>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <label className={ui.label}>Then do</label>
        {steps.map((s, i) => (
          <div key={i} className="rounded-lg border border-slate-200 p-3">
            <div className="flex items-center gap-2">
              <select className={`${ui.input} max-w-48`} value={s.tool} onChange={(e) => setStep(i, { tool: e.target.value as 'create_followup_task' | 'draft_email' })}>
                <option value="create_followup_task">Create a task</option>
                <option value="draft_email">Draft an email (never sent)</option>
              </select>
              {steps.length > 1 && <button className="text-xs text-red-500" onClick={() => setSteps(steps.filter((_, j) => j !== i))}>Remove</button>}
            </div>
            <input className={`${ui.input} mt-2`} placeholder={s.tool === 'create_followup_task' ? 'Task title, e.g. Call {lead.name} now' : 'Email subject'} value={s.a} onChange={(e) => setStep(i, { a: e.target.value })} />
            {s.tool === 'draft_email' ? (
              <textarea className={`${ui.input} mt-2`} rows={3} placeholder="Email body" value={s.b} onChange={(e) => setStep(i, { b: e.target.value })} />
            ) : (
              <div className="mt-2 flex items-center gap-2 text-sm text-slate-600">
                Due in <input className={`${ui.input.replace('w-full', 'w-20')} text-center`} inputMode="numeric" value={s.days} onChange={(e) => setStep(i, { days: e.target.value })} /> day(s)
              </div>
            )}
          </div>
        ))}
        {steps.length < 8 && <button className={ui.btnGhost} onClick={() => setSteps([...steps, { tool: 'create_followup_task', a: '', b: '', days: '1' }])}>Add step</button>}
        <p className="text-xs text-slate-400">You can use: {VARS}</p>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button className={ui.btn} disabled={busy || !name.trim() || steps.some((s) => !s.a.trim() || (s.tool === 'create_followup_task' && !/^\d{1,2}$/.test(s.days.trim())))} onClick={() => void save()}>Save workflow</button>
        <button className={ui.btnGhost} onClick={onDone}>Cancel</button>
      </div>
    </div>
  )
}

export default function Workflows() {
  const [items, setItems] = useState<Workflow[] | null>(null)
  const [runs, setRuns] = useState<WorkflowRun[]>([])
  const [leads, setLeads] = useState<Lead[]>([])
  const [testLead, setTestLead] = useState('')
  const [building, setBuilding] = useState(false)
  const [msg, setMsg] = useState('')
  const [sched, setSched] = useState<{ enabled: boolean; interval_seconds: number } | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api<Workflow[]>('/workflows').then(setItems).catch((e: Error) => setError(e.message))
    api<WorkflowRun[]>('/workflows/runs').then(setRuns).catch(() => undefined)
    api<{ enabled: boolean; interval_seconds: number }>('/workflows/scheduler/status').then(setSched).catch(() => undefined)
  }, [])

  useEffect(() => {
    load()
    api<Lead[]>('/leads').then((l) => {
      setLeads(l)
      if (l[0]) setTestLead(l[0].id)
    }).catch(() => undefined)
  }, [load])

  const act = async (fn: () => Promise<unknown>) => {
    setError('')
    setMsg('')
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    }
    load()
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold">Automations</h1>
        <div className="flex gap-2">
          <button
            className={ui.btnGhost}
            onClick={() => void act(async () => { const r = await api<{ runs: number }>('/workflows/check-inactive', { method: 'POST' }); setMsg(`Checked quiet leads: ${r.runs} workflow run(s).`) })}
          >
            Check quiet leads now
          </button>
          <button className={ui.btnGhost} onClick={() => void act(() => api('/workflows/install-defaults', { method: 'POST' }))}>Add recommended</button>
          <button className={ui.btn} onClick={() => setBuilding(true)}>New workflow</button>
        </div>
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Rules that run automatically when something happens to a lead. They use the same safe actions as the agent, so discounts still wait for approval. Each workflow runs once per lead.
        {sched && (sched.enabled ? ` Quiet leads are checked automatically every ${Math.round(sched.interval_seconds / 60)} minutes.` : ' The automatic quiet-lead check is off.')}
      </p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {msg && <p className="mt-3 text-sm text-green-700">{msg}</p>}
      {building && <Builder onDone={() => { setBuilding(false); load() }} />}

      <div className="mt-4 space-y-3">
        {items?.map((w) => (
          <div key={w.id} className={`${ui.card} ${w.enabled ? '' : 'opacity-60'}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium">{w.name}</p>
                {w.description && <p className="text-sm text-slate-500">{w.description}</p>}
                <p className="mt-2 text-sm"><span className="text-slate-400">When:</span> {w.trigger_label}</p>
                {w.conditions.map((c, i) => (
                  <p key={i} className="text-sm"><span className="text-slate-400">Only if:</span> {c.field} {OPS[c.op]} {c.value ?? ''}</p>
                ))}
                <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-sm">
                  {w.steps.map((s, i) => <li key={i}>{stepText(s)}</li>)}
                </ol>
                <p className="mt-2 text-xs text-slate-400">{w.run_count} run(s){w.last_run_at ? `, last ${new Date(w.last_run_at).toLocaleString()}` : ''}</p>
              </div>
              <div className="flex gap-2">
                <button className={ui.btnGhost} onClick={() => void act(() => api(`/workflows/${w.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !w.enabled }) }))}>
                  {w.enabled ? 'Turn off' : 'Turn on'}
                </button>
                <button className={ui.btnDanger} onClick={() => { if (confirm(`Delete "${w.name}"?`)) void act(() => api(`/workflows/${w.id}`, { method: 'DELETE' })) }}>Delete</button>
              </div>
            </div>
            {leads.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-sm">
                <span className="text-slate-500">Test on</span>
                <select className={`${ui.input} max-w-56`} value={testLead} onChange={(e) => setTestLead(e.target.value)}>
                  {leads.map((l) => <option key={l.id} value={l.id}>{l.name ?? l.email ?? 'Unknown customer'}</option>)}
                </select>
                <button className={ui.btnGhost} onClick={() => void act(async () => { await api(`/workflows/${w.id}/run`, { method: 'POST', body: JSON.stringify({ lead_id: testLead }) }); setMsg('Ran. See Recent runs below.') })}>Run now</button>
              </div>
            )}
          </div>
        ))}
        {items?.length === 0 && !building && (
          <div className={`${ui.card} text-center text-sm text-slate-500`}>
            <p>No workflows yet.</p>
            <button className={`${ui.btn} mt-3`} onClick={() => void act(() => api('/workflows/install-defaults', { method: 'POST' }))}>Add the 4 recommended workflows</button>
          </div>
        )}
      </div>

      <h2 className="mt-8 text-lg font-semibold">Recent runs</h2>
      <div className={`${ui.card} mt-3 divide-y divide-slate-100 p-0`}>
        {runs.map((r) => (
          <div key={r.id} className="px-4 py-3 text-sm">
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium">
                {r.workflow_name ?? 'Workflow'}
                {r.lead_id && <> on <Link to={`/leads/${r.lead_id}`} className="text-indigo-700 hover:underline">{r.lead_name ?? 'lead'}</Link></>}
                <span className="font-normal text-slate-400"> · {r.trigger === 'manual' ? 'manual' : r.trigger} · {new Date(r.created_at).toLocaleString()}</span>
              </p>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${runColor[r.status]}`}>{r.status}</span>
            </div>
            <ul className="mt-1 space-y-0.5 text-slate-600">
              {r.steps.map((s, i) => (
                <li key={i}>
                  <span className={`mr-2 rounded-full px-2 py-0.5 text-xs ${s.status === 'skipped' ? 'bg-slate-100 text-slate-500' : actionColor[s.status]}`}>{s.status.replace('_', ' ')}</span>
                  {toolLabel[s.tool] ?? s.tool}: {s.error ?? s.summary}
                </li>
              ))}
              {r.error && <li className="text-red-600">{r.error}</li>}
            </ul>
          </div>
        ))}
        {runs.length === 0 && <p className="px-4 py-6 text-center text-slate-500">No runs yet.</p>}
      </div>
    </div>
  )
}
