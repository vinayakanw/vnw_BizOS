import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export default function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { me, login, register } = useAuth()
  const nav = useNavigate()
  const [orgName, setOrgName] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (me) return <Navigate to="/" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register({ org_name: orgName, full_name: fullName, email, password })
      nav('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-xl border border-slate-300 bg-white px-3.5 py-3 text-[15px] outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200'

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-slate-900 p-12 text-white lg:flex">
        <p className="font-display text-xl font-bold">bizos</p>
        <div>
          <p className="max-w-md font-display text-4xl font-bold leading-tight">{mode === 'login' ? 'See what your customers asked while you were away.' : 'Your shop\'s AI assistant, ready in five minutes.'}</p>
          <p className="mt-5 max-w-md text-slate-300">{mode === 'login' ? 'Your queue is sorted by what needs you first.' : 'Add your products and a few answers, then share one chat link. No card needed.'}</p>
        </div>
        <p className="text-sm text-slate-400">Built for shops and small businesses.</p>
      </div>
      <div className="flex min-h-screen items-center justify-center p-5 lg:min-h-0">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4">
        <h1 className="text-3xl">{mode === 'login' ? 'Welcome back' : 'Set up your business'}</h1>
        {mode === 'register' && <p className="text-sm text-slate-500">It takes about five minutes. No card needed.</p>}

        {mode === 'register' && (
          <>
            <input className={input} placeholder="Business name" value={orgName} onChange={(e) => setOrgName(e.target.value)} required minLength={2} />
            <input className={input} placeholder="Your name" value={fullName} onChange={(e) => setFullName(e.target.value)} required minLength={2} />
          </>
        )}
        <input className={input} type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input className={input} type="password" placeholder="Password (at least 8 characters)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button disabled={busy} className="w-full rounded-xl bg-indigo-600 py-3 text-[15px] font-medium text-white hover:bg-indigo-700 disabled:opacity-60">
          {busy ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create my workspace'}
        </button>

        <p className="text-center text-sm text-slate-500">
          {mode === 'login' ? (
            <>No account? <Link className="text-indigo-600" to="/register">Create one</Link></>
          ) : (
            <>Already registered? <Link className="text-indigo-600" to="/login">Sign in</Link></>
          )}
        </p>
      </form>
      </div>
    </div>
  )
}
