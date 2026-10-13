import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, type IntegrationView, type Integrations as Data } from '../lib/api'
import { useAuth } from '../lib/auth'
import { ui } from '../lib/ui'

function Status({ v }: { v: IntegrationView | null }) {
  if (!v) return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">Not connected</span>
  if (v.last_error) return <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">Test failed</span>
  if (v.last_tested_at) return <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800">Working</span>
  return <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Saved, not tested</span>
}

function EmailCard({ v, canEdit, reload }: { v: IntegrationView | null; canEdit: boolean; reload: () => void }) {
  const c = v?.config
  const [f, setF] = useState({ host: '', port: '587', security: 'starttls', username: '', password: '', from_email: '', from_name: '' })
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (c) setF((x) => ({ ...x, host: String(c.host ?? ''), port: String(c.port ?? 587), security: String(c.security ?? 'starttls'), username: String(c.username ?? ''), from_email: String(c.from_email ?? ''), from_name: String(c.from_name ?? ''), password: '' }))
  }, [c])

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })

  const save = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setMsg('')
    try {
      await api('/integrations/email', { method: 'PUT', body: JSON.stringify({ ...f, port: Number(f.port) }) })
      setMsg('Saved. Send a test email to check it.')
      reload()
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setBusy(false)
    }
  }
  const test = async () => {
    setBusy(true)
    setMsg('')
    try {
      await api('/integrations/email/test', { method: 'POST' })
      setMsg('Test email sent to your login email. Check your inbox.')
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Test failed')
    } finally {
      setBusy(false)
      reload()
    }
  }
  const remove = async () => {
    if (!window.confirm('Disconnect email?')) return
    await api('/integrations/email', { method: 'DELETE' })
    setF({ host: '', port: '587', security: 'starttls', username: '', password: '', from_email: '', from_name: '' })
    reload()
  }

  return (
    <div className={ui.card}>
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Email (SMTP)</h2>
        <Status v={v} />
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Lets you send an agent's email draft from a lead page. Agents never send on their own. Gmail: host smtp.gmail.com, port 587, STARTTLS, and an app password (not your normal password).
      </p>
      <form onSubmit={save} className="mt-3 grid gap-3 sm:grid-cols-2">
        <div><label className={ui.label}>SMTP host</label><input className={ui.input} required value={f.host} onChange={set('host')} placeholder="smtp.gmail.com" disabled={!canEdit} /></div>
        <div className="flex gap-2">
          <div className="w-24"><label className={ui.label}>Port</label><input className={ui.input} required inputMode="numeric" value={f.port} onChange={set('port')} disabled={!canEdit} /></div>
          <div className="flex-1">
            <label className={ui.label}>Security</label>
            <select className={ui.input} value={f.security} onChange={set('security')} disabled={!canEdit}>
              <option value="starttls">STARTTLS (587)</option>
              <option value="ssl">SSL (465)</option>
              <option value="none">None</option>
            </select>
          </div>
        </div>
        <div><label className={ui.label}>Username</label><input className={ui.input} value={f.username} onChange={set('username')} autoComplete="off" disabled={!canEdit} /></div>
        <div><label className={ui.label}>Password {c?.has_password ? '(saved, leave blank to keep)' : ''}</label><input className={ui.input} type="password" value={f.password} onChange={set('password')} autoComplete="new-password" disabled={!canEdit} /></div>
        <div><label className={ui.label}>From email</label><input className={ui.input} type="email" required value={f.from_email} onChange={set('from_email')} disabled={!canEdit} /></div>
        <div><label className={ui.label}>From name</label><input className={ui.input} value={f.from_name} onChange={set('from_name')} placeholder="Your company" disabled={!canEdit} /></div>
        {canEdit && (
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <button className={ui.btn} disabled={busy}>Save</button>
            <button type="button" className={ui.btnGhost} disabled={busy || !v} onClick={test}>Send test email</button>
            {v && <button type="button" className={ui.btnDanger} onClick={remove}>Disconnect</button>}
          </div>
        )}
      </form>
      {msg && <p className="mt-2 text-sm text-slate-700">{msg}</p>}
      {v?.last_error && <p className="mt-2 text-sm text-red-600">Last test failed: {v.last_error}</p>}
    </div>
  )
}

function SlackCard({ v, canEdit, reload }: { v: IntegrationView | null; canEdit: boolean; reload: () => void }) {
  const [url, setUrl] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMsg('')
    try {
      await fn()
      setMsg(ok)
      setUrl('')
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Failed')
    } finally {
      setBusy(false)
      reload()
    }
  }

  return (
    <div className={ui.card}>
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Slack alerts</h2>
        <Status v={v} />
      </div>
      <p className="mt-1 text-sm text-slate-500">Posts to a channel when an action needs approval or a support ticket is opened, and lets you share a founder briefing. Create an incoming webhook in Slack and paste the URL.</p>
      {canEdit && (
        <form
          className="mt-3 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void run(() => api('/integrations/slack', { method: 'PUT', body: JSON.stringify({ webhook_url: url.trim() }) }), 'Saved. Send a test message to check it.')
          }}
        >
          <input className={`${ui.input} flex-1`} type="password" autoComplete="off" placeholder={v ? 'Webhook saved. Paste a new URL to replace it' : 'https://hooks.slack.com/services/...'} value={url} onChange={(e) => setUrl(e.target.value)} />
          <button className={ui.btn} disabled={busy || (!url.trim() && !v)}>Save</button>
          <button type="button" className={ui.btnGhost} disabled={busy || !v} onClick={() => run(() => api('/integrations/slack/test', { method: 'POST' }), 'Test message posted.')}>Send test</button>
          {v && <button type="button" className={ui.btnDanger} onClick={() => run(() => api('/integrations/slack', { method: 'DELETE' }), 'Disconnected.')}>Disconnect</button>}
        </form>
      )}
      {msg && <p className="mt-2 text-sm text-slate-700">{msg}</p>}
      {v?.last_error && <p className="mt-2 text-sm text-red-600">Last test failed: {v.last_error}</p>}
    </div>
  )
}

export default function Integrations() {
  const { me } = useAuth()
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState('')
  const canEdit = me?.role === 'owner' || me?.role === 'admin'

  const load = useCallback(() => {
    api<Data>('/integrations').then(setData).catch((e: Error) => setError(e.message))
  }, [])
  useEffect(load, [load])

  return (
    <div>
      <h1 className="text-2xl font-semibold">Email and Slack</h1>
      <p className="mt-1 text-sm text-slate-500">Connect your email so customers who leave still get your replies and quotes. Connect Slack to get a ping when something needs you. Passwords are stored encrypted and never shown again.</p>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {!canEdit && <p className="mt-3 text-sm text-amber-700">Only owners and admins can change integrations.</p>}
      {data && (
        <div className="mt-4 space-y-4">
          <EmailCard v={data.email} canEdit={canEdit} reload={load} />
          <SlackCard v={data.slack} canEdit={canEdit} reload={load} />
          <div className={ui.card}>
            <h2 className="font-semibold">WhatsApp</h2>
            <p className="mt-1 text-sm text-slate-500">Not available yet. It needs a verified Meta business account, so it comes after the core product is deployed.</p>
          </div>
        </div>
      )}
    </div>
  )
}
