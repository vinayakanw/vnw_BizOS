import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, type Order, type OrderStatus } from '../lib/api'
import { orderStatusLabel } from '../lib/leadStatus'
import { money, ui } from '../lib/ui'

type Form = {
  order_ref: string
  customer_name: string
  customer_email: string
  status: OrderStatus
  carrier: string
  tracking_id: string
  tracking_url: string
  expected_delivery: string
  items: string // "2 x Laptop; Mouse"
  total: string
  currency: string
}

const empty: Form = {
  order_ref: '', customer_name: '', customer_email: '', status: 'placed', carrier: '', tracking_id: '', tracking_url: '',
  expected_delivery: '', items: '', total: '', currency: 'INR',
}

const itemsToText = (items: Order['items']) => items.map((i) => (i.quantity > 1 ? `${i.quantity} x ${i.name}` : i.name)).join('; ')
const parseItems = (text: string) =>
  text.split(';').map((p) => p.trim()).filter(Boolean).map((p) => {
    const m = p.match(/^(\d+)\s*[xX]\s+(.+)$/)
    return m ? { name: m[2].trim(), quantity: Number(m[1]) } : { name: p, quantity: 1 }
  })

const SAMPLE = 'order_ref,customer_email,customer_name,status,carrier,tracking_id,expected_delivery,items,total\nORD-2001,asha@example.com,Asha,shipped,BlueDart,BD1234,2026-11-05,2 x DevBook 14; Mouse,109998\n'

export default function Orders() {
  const [items, setItems] = useState<Order[]>([])
  const [q, setQ] = useState('')
  const [form, setForm] = useState<Form | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const file = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setItems(await api<Order[]>(`/orders${q ? `?q=${encodeURIComponent(q)}` : ''}`))
  }, [q])

  useEffect(() => {
    const t = setTimeout(() => void load(), 250)
    return () => clearTimeout(t)
  }, [load])

  const set = (k: keyof Form, v: string) => setForm((f) => (f ? { ...f, [k]: v } : f))
  const close = () => { setForm(null); setEditId(null); setError('') }

  const startEdit = (o: Order) => {
    setEditId(o.id)
    setForm({
      order_ref: o.order_ref, customer_name: o.customer_name ?? '', customer_email: o.customer_email, status: o.status, carrier: o.carrier ?? '',
      tracking_id: o.tracking_id ?? '', tracking_url: o.tracking_url ?? '', expected_delivery: o.expected_delivery ?? '', items: itemsToText(o.items),
      total: o.total == null ? '' : String(o.total), currency: o.currency,
    })
  }

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!form) return
    setBusy(true)
    setError('')
    try {
      await api(editId ? `/orders/${editId}` : '/orders', {
        method: editId ? 'PUT' : 'POST',
        body: JSON.stringify({
          order_ref: form.order_ref, customer_name: form.customer_name || null, customer_email: form.customer_email, status: form.status,
          carrier: form.carrier || null, tracking_id: form.tracking_id || null, tracking_url: form.tracking_url || null,
          expected_delivery: form.expected_delivery || null, items: parseItems(form.items), total: form.total === '' ? null : Number(form.total), currency: form.currency,
        }),
      })
      close()
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (o: Order) => {
    if (!confirm(`Delete order ${o.order_ref}?`)) return
    await api(`/orders/${o.id}`, { method: 'DELETE' })
    await load()
  }

  const importCsv = async (f: File | undefined) => {
    if (!f) return
    setNote('')
    setError('')
    try {
      const r = await api<{ created: number; updated: number; errors: string[] }>('/orders/import', { method: 'POST', body: JSON.stringify({ csv: await f.text() }) })
      setNote(`Imported: ${r.created} new, ${r.updated} updated.${r.errors.length ? ` Skipped: ${r.errors.join(' | ')}` : ''}`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      if (file.current) file.current.value = ''
    }
  }

  const downloadSample = () => {
    const url = URL.createObjectURL(new Blob([SAMPLE], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'orders-sample.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Orders</h1>
          <p className="mt-1 text-sm text-slate-500">
            Customers who ask "where is my order?" get the real status from here. They must give the order number and the same email as on the order. Keep status and tracking up to date.
          </p>
        </div>
        <div className="flex gap-2">
          <input ref={file} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => void importCsv(e.target.files?.[0])} />
          <button className={ui.btnGhost} onClick={() => file.current?.click()}>Import CSV</button>
          <button className={ui.btn} onClick={() => { setEditId(null); setForm(empty) }}>Add order</button>
        </div>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        CSV needs order_ref and customer_email; optional: customer_name, status, carrier, tracking_id, tracking_url, expected_delivery (YYYY-MM-DD), items ("2 x Laptop; Mouse"), total.{' '}
        <button className="underline" onClick={downloadSample}>Sample file</button>
      </p>
      {note && <p className="mt-2 text-sm text-green-700">{note}</p>}
      {!form && error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {form && (
        <form onSubmit={save} className={`${ui.card} mt-4 grid gap-3 sm:grid-cols-2`}>
          <div><label className={ui.label}>Order number *</label><input className={ui.input} value={form.order_ref} onChange={(e) => set('order_ref', e.target.value)} required maxLength={60} /></div>
          <div><label className={ui.label}>Status *</label>
            <select className={ui.input} value={form.status} onChange={(e) => set('status', e.target.value)}>
              {Object.entries(orderStatusLabel).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <div><label className={ui.label}>Customer email * (must match what the customer enters in chat)</label><input className={ui.input} type="email" value={form.customer_email} onChange={(e) => set('customer_email', e.target.value)} required /></div>
          <div><label className={ui.label}>Customer name</label><input className={ui.input} value={form.customer_name} onChange={(e) => set('customer_name', e.target.value)} /></div>
          <div><label className={ui.label}>Carrier</label><input className={ui.input} value={form.carrier} onChange={(e) => set('carrier', e.target.value)} /></div>
          <div><label className={ui.label}>Tracking ID</label><input className={ui.input} value={form.tracking_id} onChange={(e) => set('tracking_id', e.target.value)} /></div>
          <div><label className={ui.label}>Tracking link (https://...)</label><input className={ui.input} value={form.tracking_url} onChange={(e) => set('tracking_url', e.target.value)} /></div>
          <div><label className={ui.label}>Expected delivery</label><input className={ui.input} type="date" value={form.expected_delivery} onChange={(e) => set('expected_delivery', e.target.value)} /></div>
          <div className="sm:col-span-2"><label className={ui.label}>Items ("2 x Laptop; Mouse")</label><input className={ui.input} value={form.items} onChange={(e) => set('items', e.target.value)} /></div>
          <div><label className={ui.label}>Total (not shown to the AI)</label><input className={ui.input} type="number" min="0" step="0.01" value={form.total} onChange={(e) => set('total', e.target.value)} /></div>
          <div><label className={ui.label}>Currency</label><input className={ui.input} maxLength={3} value={form.currency} onChange={(e) => set('currency', e.target.value.toUpperCase())} /></div>
          {error && <p className="text-sm text-red-600 sm:col-span-2">{error}</p>}
          <div className="flex gap-2 sm:col-span-2">
            <button disabled={busy} className={ui.btn}>{busy ? 'Saving...' : editId ? 'Save changes' : 'Add order'}</button>
            <button type="button" className={ui.btnGhost} onClick={close}>Cancel</button>
          </div>
        </form>
      )}

      <input className={`${ui.input} mt-4 max-w-xs`} placeholder="Search order, email or name" value={q} onChange={(e) => setQ(e.target.value)} />

      <div className={`${ui.card} mt-4 overflow-x-auto p-0`}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr><th className="px-4 py-3">Order</th><th className="px-4 py-3">Customer</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Tracking</th><th className="px-4 py-3">Total</th><th className="px-4 py-3" /></tr>
          </thead>
          <tbody>
            {items.map((o) => {
              const st = orderStatusLabel[o.status]
              return (
                <tr key={o.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium">{o.order_ref}</td>
                  <td className="px-4 py-3 text-slate-600">{o.customer_name ?? '-'}<br /><span className="text-xs text-slate-400">{o.customer_email}</span></td>
                  <td className="px-4 py-3"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${st?.cls}`}>{st?.label ?? o.status}</span></td>
                  <td className="px-4 py-3 text-slate-600">{o.carrier ?? '-'}{o.tracking_id ? ` ${o.tracking_id}` : ''}{o.expected_delivery ? <><br /><span className="text-xs text-slate-400">ETA {o.expected_delivery}</span></> : null}</td>
                  <td className="px-4 py-3">{o.total == null ? '-' : money(o.total, o.currency)}</td>
                  <td className="flex justify-end gap-2 px-4 py-3">
                    <button className={ui.btnGhost} onClick={() => startEdit(o)}>Edit</button>
                    <button className={ui.btnDanger} onClick={() => void remove(o)}>Delete</button>
                  </td>
                </tr>
              )
            })}
            {items.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No orders yet. Add one, or import a CSV.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}
