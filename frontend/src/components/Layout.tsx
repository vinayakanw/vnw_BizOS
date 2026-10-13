import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import Icon, { type IconName } from './Icon'

type Badge = 'inbox' | 'tickets' | 'approvals'
type Item = { to: string; label: string; icon: IconName; end?: boolean; badge?: Badge }
type Section = { key: string; label?: string; items: Item[]; collapsible?: boolean }

// What an owner opens every day is always visible. Everything technical lives under "More tools".
const SECTIONS: Section[] = [
  {
    key: 'daily',
    items: [
      { to: '/', label: 'Home', icon: 'home', end: true },
      { to: '/inbox', label: 'Inbox', icon: 'inbox', badge: 'inbox' },
      { to: '/approvals', label: 'Needs your OK', icon: 'ok', badge: 'approvals' },
      { to: '/leads', label: 'Leads', icon: 'leads' },
      { to: '/tickets', label: 'Support tickets', icon: 'tickets', badge: 'tickets' },
      { to: '/orders', label: 'Orders', icon: 'orders' },
    ],
  },
  {
    key: 'knows',
    label: 'What the AI knows',
    items: [
      { to: '/products', label: 'Products', icon: 'tag' },
      { to: '/faqs', label: 'FAQs', icon: 'book' },
      { to: '/documents', label: 'Documents', icon: 'file' },
    ],
  },
  {
    key: 'settings',
    label: 'Settings',
    items: [
      { to: '/profile', label: 'About your business', icon: 'shop' },
      { to: '/customer-chat', label: 'Customer chat', icon: 'chat' },
      { to: '/integrations', label: 'Email and Slack', icon: 'mail' },
    ],
  },
  {
    key: 'more',
    label: 'More tools',
    collapsible: true,
    items: [
      { to: '/analytics', label: 'Reports', icon: 'chart' },
      { to: '/founder', label: 'Weekly briefing', icon: 'spark' },
      { to: '/workflows', label: 'Automations', icon: 'bolt' },
      { to: '/activity', label: 'What the AI did', icon: 'eye' },
      { to: '/sales-agent', label: 'Try the sales AI', icon: 'flask' },
      { to: '/support-agent', label: 'Try the support AI', icon: 'flask' },
      { to: '/knowledge', label: 'Search what the AI knows', icon: 'search' },
    ],
  },
]

const OPEN_KEY = 'bizos_more_open'
const badgeCls: Record<Badge, string> = { inbox: 'bg-chilli text-white', tickets: 'bg-chilli text-white', approvals: 'bg-marigold text-slate-900' }

function loadOpen(): boolean {
  try {
    return localStorage.getItem(OPEN_KEY) === '1'
  } catch {
    return false
  }
}

const linkCls = ({ isActive }: { isActive: boolean }) =>
  `group flex items-center gap-3 rounded-xl px-3 py-2 text-[15px] transition-colors ${
    isActive ? 'bg-white/12 font-medium text-white' : 'text-slate-300 hover:bg-white/8 hover:text-white'
  }`

export default function Layout() {
  const { me, logout } = useAuth()
  const { pathname } = useLocation()
  const [counts, setCounts] = useState<Record<Badge, number>>({ inbox: 0, tickets: 0, approvals: 0 })
  const [moreOpen, setMoreOpen] = useState(loadOpen)
  const [drawer, setDrawer] = useState(false)

  // One request for all three counters (the database can be far away, so every request counts).
  useEffect(() => {
    if (!me) return
    const load = () => {
      if (document.hidden) return
      api<Record<Badge, number>>('/home/counts').then(setCounts).catch(() => undefined)
    }
    load()
    const t = setInterval(load, 20000)
    return () => clearInterval(t)
  }, [me, pathname])

  useEffect(() => setDrawer(false), [pathname])

  const inMore = useMemo(() => SECTIONS.find((s) => s.key === 'more')!.items.some((i) => pathname === i.to || pathname.startsWith(i.to + '/')), [pathname])
  const showMore = moreOpen || inMore

  const toggleMore = () => {
    const next = !moreOpen
    setMoreOpen(next)
    try {
      localStorage.setItem(OPEN_KEY, next ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  if (!me) return null
  const urgent = counts.inbox + counts.approvals

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 nav-scroll overflow-y-auto pr-1">
      {SECTIONS.map((s) => (
        <div key={s.key} className={s.label ? 'mt-5' : ''}>
          {s.label &&
            (s.collapsible ? (
              <button onClick={toggleMore} aria-expanded={showMore} className="flex w-full items-center justify-between px-3 pb-1 text-left text-[13px] text-slate-400 hover:text-white">
                {s.label}
                <Icon name="chevron" className={`h-4 w-4 transition-transform ${showMore ? 'rotate-90' : ''}`} />
              </button>
            ) : (
              <p className="px-3 pb-1 text-[13px] text-slate-400">{s.label}</p>
            ))}
          {(!s.collapsible || showMore) &&
            s.items.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={linkCls}>
                <Icon name={l.icon} />
                <span className="flex-1">{l.label}</span>
                {l.badge && counts[l.badge] > 0 && <span className={`rounded-full px-1.5 py-0.5 text-xs font-semibold ${badgeCls[l.badge]}`}>{counts[l.badge]}</span>}
              </NavLink>
            ))}
        </div>
      ))}
    </nav>
  )

  const brand = (
    <div className="mb-6 flex items-center gap-3 px-1">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500 font-display text-lg font-bold text-white">b</div>
      <div className="min-w-0">
        <p className="truncate font-display text-[17px] font-bold leading-tight text-white">{me.org.name}</p>
        {me.org.name.trim().toLowerCase() !== 'bizos' && <p className="text-xs text-slate-400">on BizOS</p>}
      </div>
    </div>
  )

  const foot = (
    <div className="mt-4 border-t border-white/10 pt-3 text-sm">
      <p className="truncate px-1 text-slate-300">{me.full_name}</p>
      <div className="mt-1 flex items-center justify-between px-1">
        <button onClick={logout} className="rounded-lg py-1 text-slate-400 hover:text-white">Sign out</button>
        <a
          href="https://www.linkedin.com/in/vinayaka-n-walishettar/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[11px] text-slate-500 hover:text-indigo-400 transition-colors"
          title="Contact Developer on LinkedIn"
        >
          Dev: Vinayaka N Walishettar
        </a>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen lg:flex">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col bg-slate-900 p-4 lg:flex">
        {brand}
        {nav}
        {foot}
      </aside>

      {/* phone: top bar and a slide-in menu */}
      <header className="sticky top-0 z-30 flex items-center justify-between bg-slate-900 px-4 py-3 text-white lg:hidden">
        <button onClick={() => setDrawer(true)} aria-label="Open menu" className="relative -ml-1 rounded-lg p-1.5">
          <Icon name="menu" className="h-6 w-6" />
          {urgent > 0 && <span className="absolute right-0 top-0 h-2.5 w-2.5 rounded-full bg-chilli" />}
        </button>
        <p className="font-display text-base font-bold">{me.org.name}</p>
        <span className="w-8" />
      </header>
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/60" onClick={() => setDrawer(false)} />
          <div className="absolute left-0 top-0 flex h-full w-72 max-w-[85%] flex-col bg-slate-900 p-4">
            <button onClick={() => setDrawer(false)} aria-label="Close menu" className="mb-2 self-end rounded-lg p-1.5 text-slate-300">
              <Icon name="close" className="h-5 w-5" />
            </button>
            {brand}
            {nav}
            {foot}
          </div>
        </div>
      )}

      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
        <div className="mx-auto max-w-5xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
