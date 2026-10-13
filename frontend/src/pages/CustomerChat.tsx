import { useEffect, useState, type FormEvent } from 'react'
import { api, type ChatSettings } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ui } from '../lib/ui'

export default function CustomerChat() {
  const { me } = useAuth()
  const [s, setS] = useState<ChatSettings | null>(null)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState('')
  const canEdit = me?.role === 'owner' || me?.role === 'admin'

  useEffect(() => {
    api<ChatSettings>('/chat/settings').then(setS).catch((e: Error) => setError(e.message))
  }, [])

  if (!s) return <p className="text-sm text-slate-500">{error || 'Loading...'}</p>

  const link = `${window.location.origin}/chat/${s.slug}`
  const embed = `<iframe src="${link}" style="width:100%;max-width:420px;height:640px;border:0;border-radius:12px" title="Chat with us"></iframe>`

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMsg('')
    setError('')
    try {
      setS(await api<ChatSettings>('/chat/settings', { method: 'PUT', body: JSON.stringify(s) }))
      setMsg('Saved.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }

  const copy = async (what: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(what)
      setTimeout(() => setCopied(''), 1500)
    } catch {
      setError('Could not copy. Select the text and copy it yourself.')
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-semibold">Customer chat</h1>
      <p className="mt-1 text-sm text-slate-500">A public page where your customers talk to your AI sales and support agents. No login for them. You answer anything the AI cannot from the Inbox.</p>
      <p className="mt-1 text-sm text-slate-500">
        Connect email in Settings, Integrations to also email customers when you reply after they leave, send quote links and let them email themselves the chat. Add your orders under Support, Orders so customers can check their order. Customers can write in English, Hindi or Hinglish and send photos, which always go to a person.
      </p>

      <form onSubmit={save} className={`${ui.card} mt-4 space-y-4`}>
        <label className="flex items-center gap-3">
          <input type="checkbox" className="h-4 w-4" checked={s.enabled} disabled={!canEdit} onChange={(e) => setS({ ...s, enabled: e.target.checked })} />
          <span className="text-sm font-medium">Chat is live {s.enabled ? '' : '(customers see "not available")'}</span>
        </label>
        <div>
          <label className={ui.label}>Link name</label>
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500">{window.location.origin}/chat/</span>
            <input className={`${ui.input} max-w-xs`} value={s.slug} disabled={!canEdit} onChange={(e) => setS({ ...s, slug: e.target.value.toLowerCase() })} />
          </div>
        </div>
        <div>
          <label className={ui.label}>Welcome message</label>
          <textarea className={ui.input} rows={2} maxLength={500} disabled={!canEdit} value={s.welcome_message} onChange={(e) => setS({ ...s, welcome_message: e.target.value })} />
        </div>
        <div className="flex flex-wrap gap-6 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={s.sales_enabled} disabled={!canEdit} onChange={(e) => setS({ ...s, sales_enabled: e.target.checked })} /> Offer sales chat ("I want to buy")</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={s.support_enabled} disabled={!canEdit} onChange={(e) => setS({ ...s, support_enabled: e.target.checked })} /> Offer support chat ("I need help")</label>
        </div>
        {canEdit ? <button className={ui.btn} disabled={busy}>Save</button> : <p className="text-sm text-amber-700">Only owners and admins can change this.</p>}
        {msg && <p className="text-sm text-green-700">{msg}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </form>

      <div className={`${ui.card} mt-4`}>
        <p className="text-xs font-medium uppercase text-slate-500">Share it</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input readOnly className={`${ui.input} flex-1`} value={link} onFocus={(e) => e.target.select()} />
          <button className={ui.btnGhost} onClick={() => copy('link', link)}>{copied === 'link' ? 'Copied' : 'Copy link'}</button>
          <a className={ui.btnGhost} href={link} target="_blank" rel="noreferrer">Open</a>
        </div>
        <p className="mt-4 text-sm text-slate-600">Or put it on your website:</p>
        <div className="mt-2 flex items-start gap-2">
          <textarea readOnly className={`${ui.input} flex-1 font-mono text-xs`} rows={3} value={embed} onFocus={(e) => e.target.select()} />
          <button className={ui.btnGhost} onClick={() => copy('embed', embed)}>{copied === 'embed' ? 'Copied' : 'Copy'}</button>
        </div>
        {!s.enabled && <p className="mt-3 text-sm text-amber-700">Chat is off right now. Turn it on and save before sharing the link.</p>}
      </div>

      <div className={`${ui.card} mt-4 text-sm text-slate-600`}>
        <p className="font-medium text-slate-800">What customers can and cannot see</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>They see only the chat: replies, and a ticket reference if support opens one.</li>
          <li>Lead scores, internal notes, quotes waiting for approval and agent steps stay private.</li>
          <li>Anything involving discounts, refunds or orders is handed to a person. Nothing is promised by the AI.</li>
        </ul>
      </div>
    </div>
  )
}
