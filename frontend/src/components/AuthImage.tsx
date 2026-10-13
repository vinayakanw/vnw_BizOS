import { useEffect, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Staff photos need the login cookie, so they are fetched with credentials and shown from a blob URL.
export default function AuthImage({ path, className = '' }: { path: string; className?: string }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let url: string | null = null
    let alive = true
    fetch(`${API_URL}${path}`, { credentials: 'include' })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => {
        if (!alive) return
        url = URL.createObjectURL(b)
        setSrc(url)
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
      if (url) URL.revokeObjectURL(url)
    }
  }, [path])
  if (failed) return <p className="text-xs text-red-600">Could not load the photo</p>
  if (!src) return <div className="h-24 w-32 animate-pulse rounded-xl bg-slate-200" />
  return (
    <a href={src} target="_blank" rel="noreferrer">
      <img src={src} alt="Customer photo" className={className} />
    </a>
  )
}
