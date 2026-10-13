import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/Icon'
import { api, type QueueItem, type SetupStep, type Today } from '../lib/api'
import { ago, ui } from '../lib/ui'

const edge: Record<QueueItem['urgency'], string> = { high: 'bg-chilli', medium: 'bg-marigold', normal: 'bg-indigo-300' }

function greeting(name: string) {
  const h = new Date().getHours()
  return `${h < 5 ? 'Still up' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'}, ${name}`
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

// The headline is a sentence about the owner's actual day, built from the real numbers.
function headline(t: Today, setupLeft: number): string {
  const { inbox, approvals } = t.counts
  if (inbox > 0) return `${plural(inbox, 'customer is', 'customers are')} waiting for you.`
  if (approvals > 0) return `The AI needs your OK on ${plural(approvals, 'thing', 'things')}.`
  if (t.queue.length > 0) return `Nothing urgent. ${plural(t.queue.length, 'thing is', 'things are')} worth a look.`
  if (setupLeft > 0) return 'Let us get you ready for customers.'
  return 'You are all caught up.'
}

function Row({ q }: { q: QueueItem }) {
  return (
    <li className="relative">
      <span className={`absolute inset-y-0 left-0 w-1 rounded-full ${edge[q.urgency]}`} />
      <Link to={q.to} className="flex items-center gap-4 py-3.5 pl-5 pr-1 hover:bg-slate-50 sm:pr-3">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{q.title}</p>
          {q.detail && <p className="truncate text-sm text-slate-500">{q.detail}</p>}
        </div>
        <span className="hidden shrink-0 text-sm text-slate-400 sm:block">{ago(q.at)}</span>
        <span className="shrink-0 rounded-xl border border-slate-300 bg-white px-3.5 py-1.5 text-sm font-medium text-indigo-700">{q.action}</span>
      </Link>
    </li>
  )
}

function Setup({ steps, onSample, seeding, error }: { steps: SetupStep[]; onSample: () => void; seeding: boolean; error: string }) {
  const required = steps.filter((s) => !s.optional)
  const done = steps.filter((s) => s.done).length
  const current = steps.find((s) => !s.done && !s.optional) ?? steps.find((s) => !s.done)
  return (
    <section className={`${ui.card} lg:sticky lg:top-8`}>
      <h2 className="text-lg font-bold">Get ready for customers</h2>
      <p className="mt-0.5 text-sm text-slate-500">{done} of {steps.length} done{required.every((s) => s.done) ? '. The rest is optional.' : ''}</p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-leaf transition-all duration-500" style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ol className="mt-4 space-y-1">
        {steps.map((s, i) => {
          const isCurrent = current?.key === s.key
          const external = s.to.startsWith('/chat/')
          return (
            <li key={s.key} className={`rounded-xl px-3 py-2.5 ${isCurrent ? 'bg-indigo-50 ring-1 ring-indigo-100' : ''}`}>
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${s.done ? 'bg-leaf text-white' : isCurrent ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-500'}`}>
                  {s.done ? <Icon name="check" className="h-3.5 w-3.5" /> : i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={`text-[15px] ${s.done ? 'text-slate-400 line-through' : 'font-medium'}`}>
                    {s.title}
                    {s.optional && !s.done && <span className="ml-2 text-xs font-normal text-slate-400">optional</span>}
                  </p>
                  {isCurrent && (
                    <>
                      <p className="mt-0.5 text-sm text-slate-600">{s.hint}</p>
                      {external ? (
                        <a href={s.to} target="_blank" rel="noreferrer" className={`${ui.btn} mt-2 inline-block`}>Open your chat</a>
                      ) : (
                        <Link to={s.to} className={`${ui.btn} mt-2 inline-block`}>Start</Link>
                      )}
                    </>
                  )}
                  {!isCurrent && !s.done && (
                    external ? (
                      <a href={s.to} target="_blank" rel="noreferrer" className="text-sm text-indigo-700 hover:underline">Open</a>
                    ) : (
                      <Link to={s.to} className="text-sm text-indigo-700 hover:underline">Go there</Link>
                    )
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ol>
      {!steps.find((s) => s.key === 'products')?.done && (
        <div className="mt-3 border-t border-slate-100 pt-3 text-sm text-slate-500">
          Just looking around?{' '}
          <button onClick={onSample} disabled={seeding} className="font-medium text-indigo-700 hover:underline">
            {seeding ? 'Loading...' : 'Load a sample shop'}
          </button>
          {error && <p className="mt-1 text-red-600">{error}</p>}
        </div>
      )}
    </section>
  )
}

function ChatLink({ path }: { path: string }) {
  const url = `${window.location.origin}${path}`
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch {
      /* the link is visible, they can select it */
    }
  }
  return (
    <section className={ui.card}>
      <h2 className="text-lg font-bold">Your customer chat link</h2>
      <p className="mt-0.5 text-sm text-slate-500">Put it on WhatsApp status, Instagram, your website or a visiting card.</p>
      <div className="mt-3 flex items-center gap-2 rounded-xl bg-slate-50 p-1.5 pl-3 ring-1 ring-slate-200">
        <p className="min-w-0 flex-1 truncate text-sm">{url}</p>
        <button onClick={() => void copy()} className="flex shrink-0 items-center gap-1.5 rounded-lg bg-white px-3 py-1.5 text-sm font-medium ring-1 ring-slate-200 hover:bg-slate-100">
          <Icon name={copied ? 'check' : 'copy'} className="h-4 w-4" />
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </section>
  )
}

export default function Dashboard() {
  const [t, setT] = useState<Today | null>(null)
  const [error, setError] = useState('')
  const [seeding, setSeeding] = useState(false)
  const [seedError, setSeedError] = useState('')

  const load = useCallback(() => {
    api<Today>('/home/today').then((r) => { setT(r); setError('') }).catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(() => { if (!document.hidden) load() }, 30000)
    return () => clearInterval(timer)
  }, [load])

  const seed = async () => {
    setSeeding(true)
    setSeedError('')
    try {
      await api('/demo/seed', { method: 'POST' })
      load()
    } catch (e) {
      setSeedError(e instanceof Error ? e.message : 'Could not load the sample shop')
    } finally {
      setSeeding(false)
    }
  }

  if (error && !t) {
    return (
      <div className="py-16 text-center">
        <p className="font-display text-xl font-bold">Could not load your home screen</p>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
        <button className={`${ui.btn} mt-4`} onClick={load}>Try again</button>
      </div>
    )
  }
  if (!t) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="h-4 w-40 rounded bg-slate-200" />
        <div className="h-12 w-3/4 rounded bg-slate-200" />
        <div className="h-64 rounded-2xl bg-slate-200" />
      </div>
    )
  }

  const setupLeft = t.steps.filter((s) => !s.done && !s.optional).length
  const showSetup = t.steps.some((s) => !s.done)
  const s = t.stats

  return (
    <div>
      <p className="text-slate-500">{greeting(t.first_name)}</p>
      <h1 className="mt-1 max-w-3xl text-4xl leading-[1.08] sm:text-5xl">{headline(t, setupLeft)}</h1>

      <div className={`mt-8 grid gap-6 ${showSetup || t.chat_path ? 'lg:grid-cols-5' : ''}`}>
        <div className="min-w-0 lg:col-span-3">
          {t.queue.length > 0 ? (
            <section className="overflow-hidden rounded-2xl bg-white ring-1 ring-slate-200">
              <ul className="divide-y divide-slate-100">
                {t.queue.map((q, i) => <Row key={`${q.kind}-${i}`} q={q} />)}
              </ul>
            </section>
          ) : (
            <section className={`${ui.card} py-10 text-center`}>
              <p className="font-display text-lg font-bold">{setupLeft > 0 ? 'Nothing here yet' : 'Nothing needs you right now'}</p>
              <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">
                {setupLeft > 0
                  ? 'Once customers start chatting, anything that needs a person shows up here, with a button to deal with it.'
                  : 'Chats that need a reply, quotes customers answered and urgent tickets will appear here.'}
              </p>
            </section>
          )}

          <p className="mt-5 text-sm text-slate-500">
            Last 7 days: {plural(s.chats, 'customer chat', 'customer chats')}, {plural(s.leads, 'new lead', 'new leads')}, {plural(s.quotes_sent, 'quote', 'quotes')} sent, {plural(s.tickets_resolved, 'ticket', 'tickets')} resolved.
          </p>
        </div>

        {(showSetup || t.chat_path) && (
          <div className="min-w-0 space-y-6 lg:col-span-2">
            {showSetup ? <Setup steps={t.steps} onSample={() => void seed()} seeding={seeding} error={seedError} /> : null}
            {t.chat_path && <ChatLink path={t.chat_path} />}
          </div>
        )}
      </div>
    </div>
  )
}
