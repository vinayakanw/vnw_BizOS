import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type InboxItem } from '../lib/api'
import { inboxStateLabel } from '../lib/leadStatus'
import { ui } from '../lib/ui'

const FILTERS = [
  { v: 'all', label: 'All' },
  { v: 'waiting', label: 'Needs a person' },
  { v: 'sales', label: 'Sales' },
  { v: 'support', label: 'Support' },
]

function ago(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

export default function Inbox() {
  const [items, setItems] = useState<InboxItem[] | null>(null)
  const [show, setShow] = useState('all')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api<InboxItem[]>(`/inbox?show=${show}`).then(setItems).catch((e: Error) => setError(e.message))
  }, [show])

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)
    return () => clearInterval(t)
  }, [load])

  return (
    <div>
      <h1 className="text-2xl font-semibold">Inbox</h1>
      <p className="mt-1 text-sm text-slate-500">Conversations customers started on your public chat page. Open one to read it or reply yourself. The AI stays quiet while you are handling a chat.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f.v} className={show === f.v ? ui.btn : ui.btnGhost} onClick={() => setShow(f.v)}>{f.label}</button>
        ))}
      </div>

      <div className={`${ui.card} mt-4 divide-y divide-slate-100 p-0`}>
        {items === null && <p className="p-5 text-sm text-slate-500">Loading...</p>}
        {items?.length === 0 && (
          <p className="p-5 text-sm text-slate-500">
            No customer chats yet. Turn on your public chat page under Settings, Customer chat, then share the link.
          </p>
        )}
        {items?.map((i) => {
          const st = inboxStateLabel[i.state]
          return (
            <Link key={i.id} to={`/inbox/${i.id}`} className="flex items-start gap-3 px-5 py-4 hover:bg-slate-50">
              <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${i.waiting ? 'bg-red-500' : 'bg-transparent'}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{i.customer_name ?? i.customer_email ?? 'Customer'}</p>
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">{i.mode}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${st.cls}`}>{st.label}</span>
                  {i.ticket_number && <span className="text-xs text-slate-500">{i.ticket_number}</span>}
                </div>
                <p className="mt-0.5 truncate text-sm text-slate-600">
                  {i.last_message_role === 'customer' ? '' : i.last_message_role === 'human' ? 'You: ' : 'AI: '}
                  {i.last_message}
                </p>
              </div>
              <span className="shrink-0 text-xs text-slate-400">{ago(i.last_message_at)}</span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
