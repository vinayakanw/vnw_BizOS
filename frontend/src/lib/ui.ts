export const ui = {
  input:
    'w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-[15px] outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200',
  label: 'mb-1 block text-xs font-medium text-slate-600',
  btn: 'rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60',
  btnGhost: 'rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-sm hover:bg-slate-100',
  btnDanger: 'rounded-xl border border-red-200 px-3.5 py-2 text-sm text-red-600 hover:bg-red-50',
  card: 'rounded-2xl bg-white p-5 ring-1 ring-slate-200',
}

export function money(n: number, currency: string) {
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n)
  } catch {
    return `${currency} ${n}`
  }
}

export function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}
