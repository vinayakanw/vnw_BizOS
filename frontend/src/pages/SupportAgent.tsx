import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, type SupportChatResult, type Step, type Ticket } from '../lib/api'
import { priorityColor, ticketStatusColor } from '../lib/leadStatus'
import { ui } from '../lib/ui'

type Msg = { role: 'customer' | 'agent'; text: string }

const EXAMPLES = ['What is your warranty policy?', 'Where is my order ORD-77? My email is sam@example.com']

export default function SupportAgent() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [convId, setConvId] = useState<string | null>(null)
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [steps, setSteps] = useState<Step[]>([])
  const [sources, setSources] = useState<string[]>([])
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
      const r = await api<SupportChatResult>('/agents/support/chat', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: convId, message }),
      })
      setConvId(r.conversation_id)
      setMsgs((m) => [...m, { role: 'agent', text: r.reply }])
      setTicket(r.ticket)
      setSteps(r.steps)
      setSources(r.sources)
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
    setTicket(null)
    setSteps([])
    setSources([])
    setEscalation(null)
    setError('')
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Try the support AI</h1>
          <p className="mt-1 text-sm text-slate-500">Try the support agent yourself, with the internal view. Real customers use your public chat page instead.</p>
        </div>
        <button className={ui.btnGhost} onClick={reset}>New conversation</button>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-5">
        <div className={`${ui.card} flex h-[34rem] flex-col lg:col-span-3`}>
          <div className="flex-1 space-y-3 overflow-y-auto pr-1">
            {msgs.length === 0 && (
              <div className="space-y-2 py-8 text-center text-sm text-slate-500">
                <p>Try one:</p>
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-left hover:bg-slate-50" onClick={() => setText(ex)}>
                    {ex}
                  </button>
                ))}
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
              <p className="font-semibold">Handed to a human</p>
              <p className="mt-1">{escalation}</p>
            </div>
          )}

          <div className={ui.card}>
            <p className="text-xs font-medium uppercase text-slate-500">Ticket</p>
            {ticket ? (
              <div className="mt-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <Link to={`/tickets/${ticket.id}`} className="font-semibold text-indigo-700 hover:underline">{ticket.number}</Link>
                  <span className="flex gap-1">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${priorityColor[ticket.priority]}`}>{ticket.priority}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ticketStatusColor[ticket.status]}`}>{ticket.status.replace('_', ' ')}</span>
                  </span>
                </div>
                <p className="mt-1">{ticket.subject}</p>
                <dl className="mt-2 space-y-1 text-slate-600">
                  <div>Category: {ticket.category.replace('_', ' ')}</div>
                  <div>Order: {ticket.order_reference ?? '-'}</div>
                  <div>Email: {ticket.email ?? '-'}</div>
                  <div>Phone: {ticket.phone ?? '-'}</div>
                </dl>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">No ticket. One is opened when the agent cannot fully resolve the issue.</p>
            )}
          </div>

          {sources.length > 0 && (
            <div className={ui.card}>
              <p className="text-xs font-medium uppercase text-slate-500">Answered from</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
                {sources.map((s) => <li key={s}>{s}</li>)}
              </ul>
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
