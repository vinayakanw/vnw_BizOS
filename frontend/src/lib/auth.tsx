import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, type Me } from './api'

type AuthState = {
  me: Me | null
  loading: boolean
  offline: boolean // the server could not be reached (not the same as signed out)
  retry: () => void
  login: (email: string, password: string) => Promise<void>
  register: (v: { org_name: string; full_name: string; email: string; password: string }) => Promise<void>
  logout: () => void
}

// Remembers that this browser was signed in, so the home page can show a spinner (not the landing page) while the session loads.
export function hint(on?: boolean): boolean {
  try {
    if (on === true) localStorage.setItem('bizos.hint', '1')
    else if (on === false) localStorage.removeItem('bizos.hint')
    return localStorage.getItem('bizos.hint') === '1'
  } catch {
    return false
  }
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)
  const [offline, setOffline] = useState(false)

  const loadMe = useCallback(async () => {
    if (window.location.pathname.startsWith('/chat/') || window.location.pathname.startsWith('/quote/')) {
      // Public customer pages: visitors are not staff, skip the session check.
      setLoading(false)
      return
    }
    setOffline(false)
    try {
      setMe(await api<Me>('/auth/me'))
      hint(true)
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) setOffline(true) // keep the session, the network is the problem
      else {
        setMe(null)
        hint(false)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadMe()
  }, [loadMe])

  useEffect(() => {
    const onExpired = () => {
      setMe(null)
      hint(false)
    }
    window.addEventListener('bizos:unauthorized', onExpired)
    return () => window.removeEventListener('bizos:unauthorized', onExpired)
  }, [])

  const login = async (email: string, password: string) => {
    await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    await loadMe()
  }

  const register: AuthState['register'] = async (v) => {
    await api('/auth/register', { method: 'POST', body: JSON.stringify(v) })
    await loadMe()
  }

  const logout = () => {
    setMe(null)
    hint(false)
    void api('/auth/logout', { method: 'POST' }).catch(() => undefined)
  }

  return <Ctx.Provider value={{ me, loading, offline, retry: () => { setLoading(true); void loadMe() }, login, register, logout }}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used inside AuthProvider')
  return v
}
