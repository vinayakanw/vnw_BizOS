import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { T, initialLang, saveLang, type Lang } from '../lib/chatText'

// Public customer chat. No login. Talks only to /public/chat/* with a visitor token.
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Info = { name: string; welcome_message: string; sales_enabled: boolean; support_enabled: boolean; email_enabled: boolean }
type Card = { name: string; price: number; currency: string; blurb: string; in_stock: boolean | null }
type Msg = { seq: number; role: 'customer' | 'agent' | 'human'; content: string; attachment_id?: string | null; cards?: Card[] }
type Reply = { products: Card[]; messages: Msg[]; last_seq: number; handoff: boolean; human_active: boolean; ticket: string | null }

async function pub<T>(path: string, token?: string | null, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('X-Visitor-Token', token)
  const res = await fetch(`${API_URL}/public/chat${path}`, { ...init, headers })
  if (!res.ok) {
    let detail = 'Something went wrong. Please try again.'
    try {
      const d = await res.json()
      if (typeof d.detail === 'string') detail = d.detail
      else if (Array.isArray(d.detail)) detail = 'Please check your details and try again.'
    } catch {
      /* ignore */
    }
    const err = new Error(detail) as Error & { status: number }
    err.status = res.status
    throw err
  }
  return res.json() as Promise<T>
}

function store(slug: string) {
  const key = `bizos_chat_${slug}`
  return {
    get: (): { token: string; mode: string } | null => {
      try {
        const v = localStorage.getItem(key)
        return v ? JSON.parse(v) : null
      } catch {
        return null
      }
    },
    set: (v: { token: string; mode: string }) => {
      try {
        localStorage.setItem(key, JSON.stringify(v))
      } catch {
        /* private mode: the chat still works, it just will not survive a reload */
      }
    },
    clear: () => {
      try {
        localStorage.removeItem(key)
      } catch {
        /* ignore */
      }
    },
  }
}

// Only links to this site's own quote page become clickable. Anything else stays plain text.
function Linkified({ text, label }: { text: string; label: string }) {
  const parts = text.split(/(https?:\/\/[^\s]+)/g)
  return (
    <>
      {parts.map((p, i) => {
        if (/^https?:\/\//.test(p)) {
          try {
            const u = new URL(p)
            if (u.host === window.location.host && /^\/quote\/[\w-]+$/.test(u.pathname)) {
              return (
                <a key={i} href={u.pathname} className="font-medium underline">
                  {label}
                </a>
              )
            }
          } catch {
            /* not a url */
          }
        }
        return <span key={i}>{p}</span>
      })}
    </>
  )
}

function ChatImage({ slug, id, token }: { slug: string; id: string; token: string }) {
  const [src, setSrc] = useState<string | null>(null)
  useEffect(() => {
    let url: string | null = null
    let alive = true
    fetch(`${API_URL}/public/chat/${slug}/photo/${id}`, { headers: { 'X-Visitor-Token': token } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => {
        if (!alive) return
        url = URL.createObjectURL(b)
        setSrc(url)
      })
      .catch(() => undefined)
    return () => {
      alive = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [slug, id, token])
  return src ? <img src={src} alt="" className="mb-1 max-h-64 rounded-xl" /> : <div className="mb-1 h-24 w-32 animate-pulse rounded-xl bg-slate-200" />
}

// Phone photos are 3 to 12 MB. Shrink them in the browser before sending.
async function shrink(file: File): Promise<Blob> {
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height))
  const c = document.createElement('canvas')
  c.width = Math.round(bmp.width * scale)
  c.height = Math.round(bmp.height * scale)
  c.getContext('2d')?.drawImage(bmp, 0, 0, c.width, c.height)
  return new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error('resize'))), 'image/jpeg', 0.85))
}

const field = 'w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-[15px] outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200'

export default function PublicChat() {
  const { slug = '' } = useParams()
  const [info, setInfo] = useState<Info | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const [mode, setMode] = useState<'sales' | 'support'>('sales')
  const [form, setForm] = useState({ name: '', email: '', phone: '' })
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [handoff, setHandoff] = useState(false)
  const [ticket, setTicket] = useState<string | null>(null)
  const [lang, setLang] = useState<Lang>(initialLang)
  const [emailNote, setEmailNote] = useState('')
  // a saved chat is being restored: show a placeholder instead of flashing the start form
  const [restoring, setRestoring] = useState(() => {
    try {
      return !!(new URLSearchParams(window.location.search).get('t') || store(slug).get())
    } catch {
      return false
    }
  })
  const fileRef = useRef<HTMLInputElement>(null)
  const t = T[lang]
  const lastSeq = useRef(0)
  const sending = useRef(false) // blocks a double click before state updates
  const bottom = useRef<HTMLDivElement>(null)

  const switchLang = () => {
    const next: Lang = lang === 'en' ? 'hi' : 'en'
    setLang(next)
    saveLang(next)
  }

  const remember = (list: Msg[]) => {
    lastSeq.current = Math.max(lastSeq.current, ...list.map((m) => m.seq), 0)
  }

  // Load business info, then restore a saved chat if there is one.
  useEffect(() => {
    let alive = true
    pub<Info>(`/${slug}`)
      .then(async (i) => {
        if (!alive) return
        setInfo(i)
        setMode(i.sales_enabled ? 'sales' : 'support')
        // A link from an email carries the chat token (?t=...). Use it, then take it out of the address bar.
        const fromLink = new URLSearchParams(window.location.search).get('t')
        if (fromLink) window.history.replaceState(null, '', window.location.pathname)
        const saved = fromLink ? { token: fromLink, mode: '' } : store(slug).get()
        if (saved) {
          try {
            const all = await pub<Msg[]>(`/${slug}/messages?after=0`, saved.token)
            const who = saved.mode ? { mode: saved.mode } : await pub<{ mode: string }>(`/${slug}/me`, saved.token)
            if (!alive) return
            store(slug).set({ token: saved.token, mode: who.mode })
            setToken(saved.token)
            setMode(who.mode === 'support' ? 'support' : 'sales')
            setMsgs(all)
            remember(all)
          } catch {
            store(slug).clear()
          }
        }
        if (alive) setRestoring(false)
      })
      .catch(() => {
        if (!alive) return
        setUnavailable(true)
        setRestoring(false)
      })
    return () => {
      alive = false
    }
  }, [slug])

  // Pick up replies from the team while the page is open.
  useEffect(() => {
    if (!token) return
    const timer = setInterval(() => {
      if (document.hidden) return
      pub<Msg[]>(`/${slug}/messages?after=${lastSeq.current}`, token)
        .then((n) => {
          if (n.length) {
            setMsgs((m) => [...m, ...n.filter((x) => !m.some((y) => y.seq === x.seq && y.role === x.role))])
            setError('')
            remember(n)
            if (n.some((x) => x.role === 'human')) setHandoff(true)
          }
        })
        .catch((e: Error & { status?: number }) => {
          if (e.status === 401) {
            store(slug).clear()
            setToken(null)
          }
        })
    }, 4000)
    return () => clearInterval(timer)
  }, [slug, token])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, busy])

  const start = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const s = await pub<{ token: string; messages: Msg[] }>(`/${slug}/start`, null, {
        method: 'POST',
        body: JSON.stringify({ mode, name: form.name, email: form.email, phone: form.phone || null }),
      })
      store(slug).set({ token: s.token, mode })
      lastSeq.current = 0
      setMsgs(s.messages)
      remember(s.messages)
      setHandoff(false)
      setTicket(null)
      setToken(s.token)
    } catch (err) {
      setError(err instanceof Error ? err.message : t.couldNot)
    } finally {
      setBusy(false)
    }
  }

  const send = async (e?: FormEvent, preset?: string) => {
    e?.preventDefault()
    const message = (preset ?? text).trim()
    if (!message || busy || !token || sending.current) return
    sending.current = true
    setText('')
    setError('')
    setMsgs((m) => [...m, { seq: -Date.now(), role: 'customer', content: message }])
    setBusy(true)
    try {
      const r = await pub<Reply>(`/${slug}/message`, token, { method: 'POST', body: JSON.stringify({ message }) })
      const fresh = r.messages.map((x, i) => (i === r.messages.length - 1 && r.products?.length ? { ...x, cards: r.products } : x))
      setMsgs((m) => [...m, ...fresh.filter((x) => !m.some((y) => y.seq === x.seq && y.role === x.role))])
      lastSeq.current = Math.max(lastSeq.current, r.last_seq)
      if (r.handoff) setHandoff(true)
      if (r.ticket) setTicket(r.ticket)
    } catch (err) {
      const er = err as Error & { status?: number }
      if (er.status === 401) {
        store(slug).clear()
        setToken(null)
      }
      setError(er.message)
    } finally {
      sending.current = false
      setBusy(false)
    }
  }

  const sendPhoto = async (file: File | undefined) => {
    if (!file || !token || busy) return
    setError('')
    setBusy(true)
    try {
      const blob = await shrink(file).catch(() => null)
      if (!blob) {
        setError(t.photoBad)
        return
      }
      const fd = new FormData()
      fd.append('file', blob, 'photo.jpg')
      fd.append('caption', text.trim())
      fd.append('lang', lang)
      const r = await pub<Reply>(`/${slug}/photo`, token, { method: 'POST', body: fd })
      setText('')
      setMsgs((m) => [...m, ...r.messages])
      lastSeq.current = Math.max(lastSeq.current, r.last_seq)
      setHandoff(true)
      if (r.ticket) setTicket(r.ticket)
    } catch (err) {
      setError(err instanceof Error ? err.message : t.photoBad)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const emailChat = async () => {
    if (!token) return
    setEmailNote(t.emailSending)
    try {
      const r = await pub<{ to: string }>(`/${slug}/transcript`, token, { method: 'POST' })
      setEmailNote(`${t.emailSent} ${r.to}`)
    } catch (err) {
      setEmailNote(err instanceof Error ? err.message : t.emailFail)
    }
  }

  const restart = () => {
    store(slug).clear()
    setToken(null)
    setMsgs([])
    setHandoff(false)
    setTicket(null)
    setError('')
    lastSeq.current = 0
  }

  if (unavailable) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6 text-center text-slate-600">
        <div>
          <p className="text-lg font-semibold text-slate-800">{t.unavailable}</p>
          <p className="mt-1 text-sm">{t.unavailableSub}</p>
        </div>
      </div>
    )
  }
  if (!info) return <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500">{t.loading}</div>

  const lastMsg = msgs[msgs.length - 1]
  const lastCards = lastMsg?.cards ?? []
  const talked = msgs.some((m) => m.role === 'customer')
  let chips: [string, string][] = []
  if (token && !handoff && lastMsg && lastMsg.role !== 'human') {
    if (!talked) chips = mode === 'sales' ? [[t.s1, t.s1], [t.s2, t.s2], [t.s3, t.s3]] : [[t.h1, t.h1], [t.h2, t.h2], [t.h3, t.h3]]
    else if (lastMsg.role === 'agent') {
      if (mode === 'sales') chips = lastCards.length ? [[t.wantQuote, t.quoteGeneric], [t.moreOptions, t.otherOptions], [t.talkPerson, t.personPlease]] : [[t.wantQuote, t.quoteGeneric], [t.moreOptions, t.otherOptions]]
      else chips = [[t.talkPerson, t.personPlease]]
    }
  }

  const both = info.sales_enabled && info.support_enabled

  return (
    <div className="flex h-dvh flex-col bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-sm font-semibold text-white">{info.name.slice(0, 1).toUpperCase()}</div>
          <div>
            <p className="text-[15px] font-semibold leading-tight">{info.name}</p>
            <p className="text-xs text-slate-500">{token ? (mode === 'sales' ? t.sales : t.support) : t.chatWithUs}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={switchLang} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100">
            {lang === 'en' ? 'हिंदी' : 'English'}
          </button>
          {token && (
            <button onClick={restart} className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100">
              {t.newChat}
            </button>
          )}
        </div>
      </header>

      {!token && restoring ? (
        <main className="mx-auto w-full max-w-2xl flex-1 space-y-3 px-4 py-6" aria-busy="true">
          <div className="h-12 w-2/3 animate-pulse rounded-2xl bg-white ring-1 ring-slate-200" />
          <div className="ml-auto h-10 w-1/2 animate-pulse rounded-2xl bg-indigo-100" />
          <div className="h-16 w-3/4 animate-pulse rounded-2xl bg-white ring-1 ring-slate-200" />
        </main>
      ) : !token ? (
        <main className="mx-auto w-full max-w-md flex-1 overflow-y-auto p-5">
          <p className="text-lg font-semibold">{info.welcome_message}</p>
          <form onSubmit={start} className="mt-5 space-y-4">
            {both && (
              <div className="grid grid-cols-2 gap-3">
                {(
                  [
                    ['sales', t.buy, t.buySub],
                    ['support', t.help, t.helpSub],
                  ] as const
                ).map(([m, title, sub]) => (
                  <button
                    type="button"
                    key={m}
                    onClick={() => setMode(m)}
                    className={`rounded-xl border p-3 text-left ${mode === m ? 'border-indigo-600 bg-indigo-50 ring-2 ring-indigo-200' : 'border-slate-300 bg-white hover:bg-slate-50'}`}
                  >
                    <p className="text-sm font-semibold">{title}</p>
                    <p className="mt-0.5 text-xs text-slate-500">{sub}</p>
                  </button>
                ))}
              </div>
            )}
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">{t.name}</label>
              <input className={field} required maxLength={100} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">{t.email}</label>
              <input className={field} type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} autoComplete="email" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">{t.phone}</label>
              <input className={field} type="tel" maxLength={30} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} autoComplete="tel" />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button disabled={busy} className="w-full rounded-xl bg-indigo-600 py-3 text-[15px] font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
              {busy ? t.starting : t.start}
            </button>
            <p className="text-center text-xs text-slate-400">{t.privacy}</p>
          </form>
        </main>
      ) : (
        <>
          <main className="mx-auto w-full max-w-2xl flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {msgs.map((m, i) => (
              <div key={`${m.seq}-${i}`} className={`flex ${m.role === 'customer' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[85%] ${m.role === 'customer' ? '' : 'space-y-0.5'}`}>
                  {m.role === 'human' && <p className="px-1 text-xs font-medium text-emerald-700">{t.team}</p>}
                  <p
                    className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-[15px] leading-snug ${
                      m.role === 'customer' ? 'bg-indigo-600 text-white' : m.role === 'human' ? 'bg-emerald-50 text-slate-900 ring-1 ring-emerald-200' : 'bg-white text-slate-900 ring-1 ring-slate-200'
                    }`}
                  >
                    {m.attachment_id && token && <ChatImage slug={slug} id={m.attachment_id} token={token} />}
                    <Linkified text={m.content} label={t.openQuote} />
                  </p>
                  {m.cards && m.cards.length > 0 && (
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      {m.cards.map((c) => (
                        <div key={c.name} className="rounded-2xl bg-white p-3 ring-1 ring-slate-200 shadow-sm">
                          <p className="text-[15px] font-semibold leading-snug">{c.name}</p>
                          <p className="mt-0.5 font-display text-xl font-bold text-indigo-700">{new Intl.NumberFormat('en-IN', { style: 'currency', currency: c.currency, maximumFractionDigits: 0 }).format(c.price)}</p>
                          {c.blurb && <p className="mt-1 text-xs text-slate-500">{c.blurb}</p>}
                          <div className="mt-2 flex items-center justify-between gap-2">
                            {c.in_stock !== null && <span className={`text-xs font-medium ${c.in_stock ? 'text-emerald-700' : 'text-red-600'}`}>{c.in_stock ? t.inStock : t.outStock}</span>}
                            <button type="button" disabled={busy} onClick={() => void send(undefined, t.quoteFor(c.name))} className="ml-auto rounded-lg bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60">{t.wantQuote}</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex w-fit items-center gap-1 rounded-2xl bg-white px-4 py-3 ring-1 ring-slate-200" aria-label={t.typing}>
                {[0, 150, 300].map((d) => <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${d}ms` }} />)}
              </div>
            )}
            {chips.length > 0 && !busy && (
              <div className="flex flex-wrap gap-2 pt-1">
                {chips.map(([label, say]) => (
                  <button key={label} type="button" onClick={() => void send(undefined, say)} className="rounded-full border border-indigo-200 bg-white px-3.5 py-1.5 text-sm font-medium text-indigo-700 hover:bg-indigo-50">{label}</button>
                ))}
              </div>
            )}
            {handoff && (
              <p className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 ring-1 ring-amber-200">
                {t.followUp}{ticket ? `. ${t.reference} ${ticket}` : ''}.
              </p>
            )}
            <div ref={bottom} />
          </main>
          <footer className="border-t border-slate-200 bg-white p-3">
            {error && <p className="mx-auto mb-2 max-w-2xl text-sm text-red-600">{error}</p>}
            <form onSubmit={send} className="mx-auto flex max-w-2xl gap-2">
              <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/*" className="hidden" onChange={(e) => void sendPhoto(e.target.files?.[0])} />
              <button
                type="button"
                title={t.photo}
                aria-label={t.photo}
                disabled={busy}
                onClick={() => fileRef.current?.click()}
                className="rounded-xl border border-slate-300 px-3 text-lg hover:bg-slate-100 disabled:opacity-60"
              >
                📷
              </button>
              <input className={field} placeholder={t.placeholder} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} />
              <button disabled={busy || !text.trim()} className="rounded-xl bg-indigo-600 px-5 text-[15px] font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
                {t.send}
              </button>
            </form>
            {info.email_enabled && (
              <p className="mx-auto mt-2 max-w-2xl text-xs text-slate-500">
                <button type="button" onClick={() => void emailChat()} className="underline hover:text-slate-700">
                  {t.emailChat}
                </button>
                {emailNote && <span className="ml-2">{emailNote}</span>}
              </p>
            )}
          </footer>
        </>
      )}
    </div>
  )
}
