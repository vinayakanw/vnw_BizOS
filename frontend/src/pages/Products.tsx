import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, type Product } from '../lib/api'
import { money, ui } from '../lib/ui'

type Form = {
  name: string
  sku: string
  category: string
  description: string
  price: string
  currency: string
  stock: string
  specs: string // "key: value" per line
  is_active: boolean
}

const empty: Form = {
  name: '',
  sku: '',
  category: '',
  description: '',
  price: '',
  currency: 'INR',
  stock: '',
  specs: '',
  is_active: true,
}

const parseSpecs = (text: string) => {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const i = line.indexOf(':')
    if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return out
}
const specsToText = (s: Record<string, string>) =>
  Object.entries(s)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n')

export default function Products() {
  const [items, setItems] = useState<Product[]>([])
  const [q, setQ] = useState('')
  const [form, setForm] = useState<Form | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setItems(await api<Product[]>(`/products${q ? `?q=${encodeURIComponent(q)}` : ''}`))
  }, [q])

  useEffect(() => {
    const t = setTimeout(() => void load(), 250)
    return () => clearTimeout(t)
  }, [load])

  const startEdit = (p: Product) => {
    setEditId(p.id)
    setForm({
      name: p.name,
      sku: p.sku ?? '',
      category: p.category ?? '',
      description: p.description ?? '',
      price: String(p.price),
      currency: p.currency,
      stock: p.stock == null ? '' : String(p.stock),
      specs: specsToText(p.specs),
      is_active: p.is_active,
    })
  }

  const close = () => {
    setForm(null)
    setEditId(null)
    setError('')
  }

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!form) return
    setBusy(true)
    setError('')
    const body = {
      name: form.name,
      sku: form.sku || null,
      category: form.category || null,
      description: form.description || null,
      price: Number(form.price),
      currency: form.currency,
      stock: form.stock === '' ? null : Number(form.stock),
      specs: parseSpecs(form.specs),
      is_active: form.is_active,
    }
    try {
      await api(editId ? `/products/${editId}` : '/products', {
        method: editId ? 'PUT' : 'POST',
        body: JSON.stringify(body),
      })
      close()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (p: Product) => {
    if (!confirm(`Delete "${p.name}"?`)) return
    await api(`/products/${p.id}`, { method: 'DELETE' })
    await load()
  }

  const set = (k: keyof Form, v: string | boolean) => setForm((f) => (f ? { ...f, [k]: v } : f))

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Products</h1>
        <button className={ui.btn} onClick={() => { setEditId(null); setForm(empty) }}>
          Add product
        </button>
      </div>

      {form && (
        <form onSubmit={save} className={`${ui.card} mt-4 grid gap-3 sm:grid-cols-2`}>
          <div>
            <label className={ui.label}>Name *</label>
            <input className={ui.input} value={form.name} onChange={(e) => set('name', e.target.value)} required />
          </div>
          <div>
            <label className={ui.label}>Category</label>
            <input className={ui.input} value={form.category} onChange={(e) => set('category', e.target.value)} />
          </div>
          <div>
            <label className={ui.label}>Price *</label>
            <input className={ui.input} type="number" min="0" step="0.01" value={form.price} onChange={(e) => set('price', e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={ui.label}>Currency</label>
              <input className={ui.input} maxLength={3} value={form.currency} onChange={(e) => set('currency', e.target.value.toUpperCase())} required />
            </div>
            <div>
              <label className={ui.label}>Stock</label>
              <input className={ui.input} type="number" min="0" value={form.stock} onChange={(e) => set('stock', e.target.value)} />
            </div>
          </div>
          <div>
            <label className={ui.label}>SKU</label>
            <input className={ui.input} value={form.sku} onChange={(e) => set('sku', e.target.value)} />
          </div>
          <label className="flex items-center gap-2 pt-5 text-sm">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} />
            Active (visible to the agent)
          </label>
          <div className="sm:col-span-2">
            <label className={ui.label}>Description</label>
            <textarea className={ui.input} rows={2} value={form.description} onChange={(e) => set('description', e.target.value)} />
          </div>
          <div className="sm:col-span-2">
            <label className={ui.label}>Specs (one per line, "key: value")</label>
            <textarea className={ui.input} rows={3} placeholder={'RAM: 16GB\nCPU: Ryzen 7'} value={form.specs} onChange={(e) => set('specs', e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600 sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <button disabled={busy} className={ui.btn}>{busy ? 'Saving...' : editId ? 'Save changes' : 'Create product'}</button>
            <button type="button" className={ui.btnGhost} onClick={close}>Cancel</button>
          </div>
        </form>
      )}

      <input className={`${ui.input} mt-4 max-w-xs`} placeholder="Search products" value={q} onChange={(e) => setQ(e.target.value)} />

      <div className={`${ui.card} mt-4 overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">Stock</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-3 font-medium">{p.name}</td>
                <td className="px-4 py-3 text-slate-600">{p.category ?? '-'}</td>
                <td className="px-4 py-3">{money(p.price, p.currency)}</td>
                <td className="px-4 py-3">{p.stock ?? '-'}</td>
                <td className="px-4 py-3">{p.is_active ? 'Active' : 'Hidden'}</td>
                <td className="flex justify-end gap-2 px-4 py-3">
                  <button className={ui.btnGhost} onClick={() => startEdit(p)}>Edit</button>
                  <button className={ui.btnDanger} onClick={() => void remove(p)}>Delete</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">No products yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
