import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

type Line = { who: 'customer' | 'ai'; text: string; card?: boolean }

const SCRIPT: Line[] = [
  { who: 'customer', text: 'Bhai, 10 laptop chahiye. Budget 60k each.' },
  { who: 'ai', text: 'Ye WorkBook 15 aapke budget mein fit hota hai. 10 units ke liye quote bana dun?', card: true },
  { who: 'customer', text: 'Haan, bhej do.' },
  { who: 'ai', text: 'Noted. Hamari team aapko quote aur delivery date confirm karegi.' },
]

function useDemo() {
  const [shown, setShown] = useState(0)
  const [typing, setTyping] = useState(false)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setShown(SCRIPT.length)
      return
    }
    let dead = false
    const timers: number[] = []
    const wait = (ms: number, fn: () => void) => timers.push(window.setTimeout(() => !dead && fn(), ms))
    const play = (i: number) => {
      if (i >= SCRIPT.length) {
        wait(6000, () => {
          setShown(0)
          wait(900, () => play(0))
        })
        return
      }
      if (SCRIPT[i].who === 'ai') {
        setTyping(true)
        wait(1300, () => {
          setTyping(false)
          setShown(i + 1)
          wait(1500, () => play(i + 1))
        })
      } else {
        wait(i === 0 ? 900 : 700, () => {
          setShown(i + 1)
          wait(800, () => play(i + 1))
        })
      }
    }
    play(0)
    return () => {
      dead = true
      timers.forEach(clearTimeout)
    }
  }, [])

  return { shown, typing }
}

function PhoneChat() {
  const { shown, typing } = useDemo()
  return (
    <div className="mx-auto w-full max-w-[22rem]">
      <p className="mb-3 flex items-center gap-2 text-sm font-medium text-marigold">
        <span className="h-2 w-2 rounded-full bg-marigold" />
        11:04 pm. Your shop is closed.
      </p>
      <div className="overflow-hidden rounded-[1.75rem] bg-slate-50 text-slate-900 shadow-2xl ring-1 ring-white/10">
        <div className="flex items-center gap-3 bg-white px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 font-display font-bold text-white">S</span>
          <div>
            <p className="text-sm font-semibold leading-tight">Sharma Electronics</p>
            <p className="text-xs text-slate-500">Sales</p>
          </div>
        </div>
        <div className="h-[25rem] space-y-2.5 overflow-hidden p-4" aria-live="off">
          {SCRIPT.slice(0, shown).map((l, i) => (
            <div key={i} className={`flex ${l.who === 'customer' ? 'justify-end' : 'justify-start'}`}>
              <div className="max-w-[85%]">
                <p className={`rounded-2xl px-3.5 py-2 text-[14px] leading-snug ${l.who === 'customer' ? 'bg-indigo-600 text-white' : 'bg-white text-slate-900 ring-1 ring-slate-200'}`}>{l.text}</p>
                {l.card && (
                  <div className="mt-2 rounded-2xl bg-white p-3 ring-1 ring-slate-200">
                    <p className="text-sm font-semibold">WorkBook 15</p>
                    <p className="font-display text-lg font-bold text-indigo-700">₹48,999</p>
                    <div className="mt-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-leaf">In stock</span>
                      <span className="rounded-md bg-indigo-600 px-2 py-1 font-medium text-white">Get a quote</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {typing && (
            <div className="flex w-fit items-center gap-1 rounded-2xl bg-white px-3.5 py-3 ring-1 ring-slate-200">
              {[0, 150, 300].map((d) => (
                <span key={d} className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${d}ms` }} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ edge, title, detail, tag }: { edge: string; title: string; detail: string; tag: string }) {
  return (
    <div className={`flex items-center gap-3 border-l-4 ${edge} bg-white px-4 py-3.5`}>
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title}</p>
        <p className="text-sm text-slate-500">{detail}</p>
      </div>
      <span className="shrink-0 rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-indigo-700">{tag}</span>
    </div>
  )
}

const HANDLES = [
  ['Sales questions', 'Answers from the products and prices you list. Asks for quantity and budget, picks the best fit, and prepares the quote.'],
  ['Support', 'Order status from your own order list. Returns and warranty from your FAQs. In English, Hindi or Hinglish.'],
  ['Hand-offs', 'Discounts, refunds and anything it cannot answer come to you with the reason. You can take over any chat at any time.'],
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <section className="bg-slate-900 text-white">
        <div className="mx-auto max-w-6xl px-5">
          <nav className="flex items-center justify-between py-5">
            <p className="font-display text-xl font-bold">bizos</p>
            <div className="flex items-center gap-2">
              <Link to="/login" className="rounded-xl px-4 py-2 text-sm font-medium text-slate-200 hover:text-white">Sign in</Link>
              <Link to="/register" className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100">Start free</Link>
            </div>
          </nav>
          <div className="grid items-center gap-12 pb-16 pt-8 lg:grid-cols-[1.1fr_1fr] lg:pb-24 lg:pt-14">
            <div>
              <h1 className="max-w-xl text-5xl leading-[1.05] sm:text-6xl">Answer every customer, even at 11 pm.</h1>
              <p className="mt-6 max-w-lg text-lg text-slate-300">
                BizOS is an AI assistant for your shop. It replies to buyers on your chat link, quotes prices from your own product list, checks order status, and brings you in only when a person is needed.
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link to="/register" className="rounded-xl bg-indigo-500 px-6 py-3.5 text-base font-semibold text-white hover:bg-indigo-400">Start free</Link>
                <a href="#morning" className="rounded-xl px-5 py-3.5 text-base font-medium text-slate-200 ring-1 ring-white/25 hover:bg-white/5">See what you get in the morning</a>
              </div>
              <p className="mt-4 text-sm text-slate-400">No card needed. Works in English, Hindi and Hinglish.</p>
            </div>
            <PhoneChat />
          </div>
        </div>
      </section>

      <section id="morning" className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
        <div className="grid items-center gap-10 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <p className="text-base font-medium text-slate-500">7:30 am</p>
            <h2 className="mt-1 text-4xl leading-tight">Open BizOS. It is already sorted.</h2>
            <p className="mt-4 max-w-md text-lg text-slate-600">What needs you comes first. Everything the AI already handled is out of your way, with the full chat one click behind it.</p>
          </div>
          <div className="overflow-hidden rounded-2xl ring-1 ring-slate-200">
            <div className="divide-y divide-slate-200">
              <Row edge="border-chilli" title="Rohan wants 10 laptops" detail="WorkBook 15, ₹48,999 each. Quote ready to send." tag="Open lead" />
              <Row edge="border-marigold" title="Approve a discount?" detail="Rohan asked for 8% off. Over your 5% limit." tag="Review" />
              <Row edge="border-leaf" title="Priya's order question" detail="Answered by the AI with the tracking status. No action needed." tag="Done" />
            </div>
          </div>
        </div>
      </section>

      <section className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-5 py-16 lg:py-24">
          <h2 className="max-w-xl text-4xl leading-tight">What it handles, and what it leaves to you</h2>
          <div className="mt-10 divide-y divide-slate-200">
            {HANDLES.map(([title, text]) => (
              <div key={title} className="grid gap-2 py-6 md:grid-cols-[16rem_1fr] md:gap-10">
                <h3 className="font-display text-2xl font-bold">{title}</h3>
                <p className="max-w-xl text-lg text-slate-600">{text}</p>
              </div>
            ))}
          </div>
          <p className="mt-6 max-w-xl text-lg font-medium">It never invents a price and it never promises a refund. If it is not in your data, it says so and calls you.</p>
        </div>
      </section>

      <section className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-5 py-14 md:flex-row md:items-center">
          <div>
            <h2 className="text-3xl">Set up in about five minutes.</h2>
            <p className="mt-2 text-slate-300">Add your products and a few answers. Share one link. No card needed.</p>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/register" className="rounded-xl bg-indigo-500 px-6 py-3.5 font-semibold text-white hover:bg-indigo-400">Start free</Link>
            <Link to="/login" className="rounded-xl px-5 py-3.5 font-medium text-slate-200 ring-1 ring-white/25 hover:bg-white/5">Sign in</Link>
          </div>
        </div>
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-2 px-5 pb-8 text-sm text-slate-400 sm:flex-row sm:items-center">
          <p>BizOS. Built for shops and small businesses in India.</p>
          <p>
            Developed by{' '}
            <a
              href="https://www.linkedin.com/in/vinayaka-n-walishettar/"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-slate-300 underline underline-offset-4 hover:text-white"
            >
              Vinayaka N Walishettar
            </a>
          </p>
        </div>
      </section>
    </div>
  )
}
