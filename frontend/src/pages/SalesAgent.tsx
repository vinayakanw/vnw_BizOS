import { useEffect, useRef, useState, type FormEvent } from 'react'
import { actionColor, toolLabel } from '../lib/leadStatus'
import { api, type ActionResult, type ChatResult, type Lead, type ProductMatch, type Step } from '../lib/api'
import { money, ui } from '../lib/ui'

type Msg = { role: 'customer' | 'agent'; text: string }

const statusColor: Record<string, string> = {
  HOT: 'bg-red-100 text-red-700',
  WARM: 'bg-amber-100 text-amber-800',
  QUALIFYING: 'bg-sky-100 text-sky-800',
  NEW: 'bg-slate-100 text-slate-700',
}

const EXAMPLE = 'Hi, I need 15 laptops for my startup. My budget is around Rs 60,000 per laptop. Do you have something suitable?'

export default function SalesAgent() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [convId, setConvId] = useState<string | null>(null)
  const [lead, setLead] = useState<Lead | null>(null)
  const [steps, setSteps] = useState<Step[]>([])
  const [products, setProducts] = useState<ProductMatch[]>([])
  const [actions, setActions] = useState<ActionResult[]>([])
  const [escalation, setEscalation] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, busy])

  const send = async (e?: FormEvent) => {
    e?.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    setText('')
    setError('')
    setMsgs((m) => [...m, { role: 'customer', text: message }])
    setBusy(true)
    try {
      const r = await api<ChatResult>('/agents/sales/chat', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: convId, message }),
      })
      setConvId(r.conversation_id)
      setMsgs((m) => [...m, { role: 'agent', text: r.reply }])
      setLead(r.lead)
      setSteps(r.steps)
      setProducts(r.products)
      setActions(r.actions)
      setEscalation(r.escalated ? r.escalation_reason : null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const reset = () => {
    setMsgs([])
    setConvId(null)
    setLead(null)
    setSteps([])
    setProducts([])
    setActions([])
    setEscalation(null)
    setError('')
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Try the sales AI</h1>
          <p className="mt-1 text-sm text-slate-500">Try the sales agent yourself, with the internal view: lead score, proposed actions and agent steps. Real customers use your public chat page instead.</p>
        </div>
        <button className={ui.btnGhost} onClick={reset}>New conversation</button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <div className={`${ui.card} flex h-[34rem] flex-col lg:col-span-3`}>
          <div className="flex-1 space-y-3 overflow-y-auto pr-1">
            {msgs.length === 0 && (
              <div className="py-8 text-center text-sm text-slate-500">
                <p>Try the example from the spec:</p>
                <button className="mt-2 rounded-lg border border-slate-300 px-3 py-2 text-left hover:bg-slate-50" onClick={() => setText(EXAMPLE)}>
                  {EXAMPLE}
                </button>
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'customer' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${m.role === 'customer' ? 'bg-indigo-600 text-white' : 'bg-slate-100'}`}>
                  {m.text}
                </div>
              </div>
            ))}
            {busy && <p className="text-sm text-slate-400">Agent is working...</p>}
            <div ref={bottom} />
          </div>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          <form onSubmit={send} className="mt-3 flex gap-2">
            <input className={ui.input} placeholder="Type a customer message" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
            <button disabled={busy || !text.trim()} className={ui.btn}>Send</button>
          </form>
        </div>

        <div className="space-y-4 lg:col-span-2">
          {escalation && (
            <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-semibold">Human approval needed</p>
              <p className="mt-1">{escalation}</p>
            </div>
          )}

          <div className={ui.card}>
            <p className="text-xs font-medium uppercase text-slate-500">Lead</p>
            {lead ? (
              <div className="mt-2 text-sm">
                <div className="flex items-center justify-between">
                  <p className="font-semibold">{lead.name ?? 'Unknown customer'}{lead.company ? `, ${lead.company}` : ''}</p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColor[lead.status] ?? statusColor.NEW}`}>{lead.status}</span>
                </div>
                <p className="mt-2 text-3xl font-semibold">{lead.score}<span className="text-base font-normal text-slate-400">/100</span></p>
                <dl className="mt-2 space-y-1 text-slate-600">
                  <div>Requirement: {lead.requirement ?? '-'}</div>
                  <div>Quantity: {lead.quantity ?? '-'}</div>
                  <div>Budget per unit: {lead.budget_per_unit ? money(lead.budget_per_unit, lead.currency ?? 'INR') : '-'}</div>
                  <div>Potential value: {lead.potential_value ? money(lead.potential_value, lead.currency ?? 'INR') : '-'}</div>
                  <div>Intent: {lead.intent}</div>
                </dl>
                <ul className="mt-2 list-disc pl-5 text-slate-600">
                  {lead.score_reasons.map((r) => <li key={r}>{r}</li>)}
                </ul>
                <p className="mt-3 rounded-lg bg-slate-50 p-2 font-medium">Next: {lead.next_action}</p>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">No lead yet. A lead is created when the customer shows buying interest.</p>
            )}
          </div>

          {products.length > 0 && (
            <div className={ui.card}>
              <p className="text-xs font-medium uppercase text-slate-500">Products considered</p>
              <ul className="mt-2 space-y-1 text-sm">
                {products.map((p) => (
                  <li key={p.name} className="flex justify-between gap-2">
                    <span>{p.name}</span>
                    <span className={p.within_budget === false ? 'text-red-600' : 'text-slate-600'}>{money(p.price, p.currency)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {actions.length > 0 && (
            <div className={ui.card}>
              <p className="text-xs font-medium uppercase text-slate-500">Actions proposed by the agent</p>
              <ul className="mt-2 space-y-2 text-sm">
                {actions.map((a) => (
                  <li key={a.id}>
                    <span className={`mr-2 rounded-full px-2 py-0.5 text-xs font-medium ${actionColor[a.status]}`}>{a.status.replace('_', ' ')}</span>
                    <span className="font-medium">{toolLabel[a.tool] ?? a.tool}</span>
                    <p className="mt-0.5 text-slate-600">{a.error ?? a.summary}</p>
                  </li>
                ))}
              </ul>
              {actions.some((a) => a.status === 'pending_approval') && (
                <p className="mt-2 text-xs text-amber-700">Waiting in Approvals. Nothing happens until you approve.</p>
              )}
            </div>
          )}

          {steps.length > 0 && (
            <div className={ui.card}>
              <p className="text-xs font-medium uppercase text-slate-500">What the agent did</p>
              <ol className="mt-2 space-y-1.5 text-sm">
                {steps.map((s, i) => (
                  <li key={i}>
                    <span className="font-medium">{s.step}</span>
                    {s.detail && <span className="text-slate-500">: {s.detail}</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
