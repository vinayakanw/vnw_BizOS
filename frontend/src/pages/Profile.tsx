import { useEffect, useState, type FormEvent } from 'react'
import { api, type Profile as ProfileT } from '../lib/api'
import { ui } from '../lib/ui'

export default function Profile() {
  const [p, setP] = useState<ProfileT | null>(null)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<ProfileT>('/profile').then(setP).catch((e: Error) => setError(e.message))
  }, [])

  if (!p) return <p className="text-sm text-slate-500">{error || 'Loading...'}</p>

  const set = (k: keyof ProfileT, v: string) => setP({ ...p, [k]: v })
  const v = (k: keyof ProfileT) => p[k] ?? ''

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMsg('')
    setError('')
    const clean = (s: string | null) => (s && s.trim() ? s.trim() : null)
    try {
      const out = await api<ProfileT>('/profile', {
        method: 'PUT',
        body: JSON.stringify({
          industry: clean(p.industry),
          website: clean(p.website),
          description: clean(p.description),
          target_customers: clean(p.target_customers),
          tone: clean(p.tone),
          discount_policy: clean(p.discount_policy),
          support_email: clean(p.support_email),
        }),
      })
      setP(out)
      setMsg('Saved')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">About your business</h1>
      <p className="mt-1 text-sm text-slate-500">What the AI should know about you: what you sell, who your customers are, how you talk. It will never offer a discount you did not write here.</p>
      <form onSubmit={save} className={`${ui.card} mt-4 grid gap-3 sm:grid-cols-2`}>
        <div>
          <label className={ui.label}>Business name</label>
          <input className={ui.input} value={p.name} disabled />
        </div>
        <div>
          <label className={ui.label}>Industry</label>
          <input className={ui.input} value={v('industry')} onChange={(e) => set('industry', e.target.value)} />
        </div>
        <div>
          <label className={ui.label}>Website</label>
          <input className={ui.input} value={v('website')} onChange={(e) => set('website', e.target.value)} />
        </div>
        <div>
          <label className={ui.label}>Support email</label>
          <input className={ui.input} type="email" value={v('support_email')} onChange={(e) => set('support_email', e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className={ui.label}>What does your business do?</label>
          <textarea className={ui.input} rows={3} value={v('description')} onChange={(e) => set('description', e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className={ui.label}>Target customers</label>
          <textarea className={ui.input} rows={2} value={v('target_customers')} onChange={(e) => set('target_customers', e.target.value)} />
        </div>
        <div>
          <label className={ui.label}>Brand tone</label>
          <input className={ui.input} placeholder="friendly, professional" value={v('tone')} onChange={(e) => set('tone', e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className={ui.label}>Discount policy</label>
          <textarea className={ui.input} rows={2} placeholder="Up to 5% on 10+ units. Anything higher needs owner approval." value={v('discount_policy')} onChange={(e) => set('discount_policy', e.target.value)} />
        </div>
        {error && <p className="text-sm text-red-600 sm:col-span-2">{error}</p>}
        {msg && <p className="text-sm text-green-600 sm:col-span-2">{msg}</p>}
        <div className="sm:col-span-2">
          <button disabled={busy} className={ui.btn}>{busy ? 'Saving...' : 'Save profile'}</button>
        </div>
      </form>
    </div>
  )
}
