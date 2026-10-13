const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
// Sessions live in httpOnly cookies set by the API. JavaScript never sees a token.
try {
  localStorage.removeItem('bizos_token') // leftover from older versions
} catch {
  /* ignore */
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function errorMessage(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d: { loc?: string[]; msg?: string }) => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ')
  }
  return fallback
}

let refreshing: Promise<boolean> | null = null

// One refresh at a time, shared by every request that hit a 401 at the same moment.
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_URL}/auth/refresh`, { method: 'POST', credentials: 'include' })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

const NO_REFRESH = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout']

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  // Let the browser set the multipart boundary for FormData.
  if (!(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  // A slow or missing connection should end in a clear message, not an endless spinner.
  const limit = init.body instanceof FormData ? 120_000 : 30_000
  const send = async () => {
    try {
      return await fetch(`${API_URL}${path}`, { ...init, headers, credentials: 'include', signal: init.signal ?? AbortSignal.timeout(limit) })
    } catch {
      throw new ApiError(0, "Can't reach the server. Check your internet connection and try again.")
    }
  }
  let res = await send()
  if (res.status === 401 && !NO_REFRESH.includes(path)) {
    if (await refreshSession()) {
      res = await send()
    }
    if (res.status === 401) {
      // Refresh failed too: the session is over. Let the app send the user to the login page.
      window.dispatchEvent(new Event('bizos:unauthorized'))
    }
  }
  if (!res.ok) {
    let data: unknown = null
    try {
      data = await res.json()
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, errorMessage(data, res.statusText))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export type Me = {
  id: string
  email: string
  full_name: string
  role: string
  org: { id: string; name: string }
}

export type Product = {
  id: string
  name: string
  sku: string | null
  category: string | null
  description: string | null
  price: number
  currency: string
  stock: number | null
  specs: Record<string, string>
  is_active: boolean
}

export type Faq = { id: string; question: string; answer: string; category: string | null }

export type DocumentRow = {
  id: string
  filename: string
  content_type: string | null
  size_bytes: number
  status: string
  chunk_count: number
  created_at: string
}

export type SearchHit = {
  chunk_id: string
  source_type: 'document' | 'faq'
  source_id: string
  title: string
  content: string
  score: number
}

export type Profile = {
  name: string
  industry: string | null
  website: string | null
  description: string | null
  target_customers: string | null
  tone: string | null
  discount_policy: string | null
  support_email: string | null
}

export type Lead = {
  id: string
  name: string | null
  company: string | null
  email: string | null
  phone: string | null
  requirement: string | null
  use_case: string | null
  timeline: string | null
  quantity: number | null
  budget_per_unit: number | null
  currency: string | null
  potential_value: number | null
  purchase_stage: string
  intent: 'LOW' | 'MEDIUM' | 'HIGH'
  score: number
  status: 'NEW' | 'QUALIFYING' | 'WARM' | 'HOT' | 'CONVERTED' | 'LOST'
  score_reasons: string[]
  next_action: string | null
  last_interaction_at: string | null
  created_at: string
}

export type Note = { id: string; author_name: string; body: string; created_at: string }
export type ChatMessage = { id: string; conversation_id: string; seq: number; role: 'customer' | 'agent' | 'human'; content: string; created_at: string; attachment_id?: string | null }
export type LeadConversation = {
  id: string
  escalated: boolean
  escalation_reason: string | null
  created_at: string
  messages: ChatMessage[]
}
export type Quote = {
  id: string
  number: string
  items: { product: string; unit_price: number; quantity: number; line_total: number }[]
  currency: string
  subtotal: number
  discount_pct: number
  total: number
  status: string
  public_token: string | null
  customer_response: 'accepted' | 'declined' | 'changes_requested' | null
  customer_note: string | null
  responded_at: string | null
  expires_at: string | null
  created_at: string
}
export type Task = { id: string; title: string; due_at: string | null; status: 'open' | 'done'; created_by: string }
export type ToolCall = {
  id: string
  lead_id: string | null
  lead_name: string | null
  tool: string
  args: Record<string, unknown>
  summary: string
  status: 'executed' | 'pending_approval' | 'rejected' | 'failed'
  approval_reason: string | null
  result: Record<string, unknown> | null
  error: string | null
  decided_by: string | null
  decided_at: string | null
  created_at: string
}
export type ActionResult = { id: string; tool: string; status: ToolCall['status']; summary: string; error: string | null }
export type LeadDetail = { lead: Lead; notes: Note[]; conversations: LeadConversation[]; quotes: Quote[]; tasks: Task[]; tool_calls: ToolCall[] }
export type Pipeline = {
  counts: Record<string, number>
  open_value: number
  won_value: number
  lost_value: number
  total: number
  conversion_rate: number
}

export type Step = { t: string; step: string; detail: string }

export type ProductMatch = {
  name: string
  price: number
  currency: string
  stock: number | null
  within_budget: boolean | null
}

export type ChatResult = {
  conversation_id: string
  reply: string
  escalated: boolean
  escalation_reason: string | null
  lead: Lead | null
  run_id: string
  steps: Step[]
  products: ProductMatch[]
  actions: ActionResult[]
}

export type Run = {
  id: string
  agent: string
  conversation_id: string | null
  status: 'running' | 'completed' | 'escalated' | 'failed'
  summary: string | null
  steps: Step[]
  error: string | null
  duration_ms: number | null
  created_at: string
}

export type WorkflowStep = {
  tool: 'create_quote' | 'create_followup_task' | 'draft_email'
  args: Record<string, string | number>
  condition?: { field: string; op: string; value?: string | number | null } | null
}
export type Workflow = {
  id: string
  name: string
  description: string | null
  trigger: string
  trigger_label: string
  enabled: boolean
  conditions: { field: string; op: string; value?: string | number | null }[]
  steps: WorkflowStep[]
  run_count: number
  last_run_at: string | null
  created_at: string
}
export type WorkflowRun = {
  id: string
  workflow_id: string
  workflow_name: string | null
  lead_id: string | null
  lead_name: string | null
  trigger: string
  status: 'completed' | 'partial' | 'failed'
  steps: { tool: string; status: string; summary: string; error: string | null }[]
  error: string | null
  created_at: string
}

export type Report = {
  metric: string
  title: string
  window_days: number | null
  facts: Record<string, number | string>
  columns: string[]
  rows: (string | number | boolean)[][]
}
export type AskResult = { answer: string; results: Report[]; run_id: string; steps: Step[]; out_of_scope: boolean }
export type Overview = { pipeline: Report; leads_over_time: Report; stale: Report; tasks: Report }

export type Ticket = {
  id: string
  conversation_id: string
  number: string
  subject: string
  category: string
  priority: 'low' | 'normal' | 'high'
  status: 'open' | 'in_progress' | 'resolved'
  customer_name: string | null
  email: string | null
  phone: string | null
  order_reference: string | null
  escalation_reason: string | null
  created_at: string
  updated_at: string | null
}
export type SupportChatResult = {
  conversation_id: string
  reply: string
  escalated: boolean
  escalation_reason: string | null
  ticket: Ticket | null
  run_id: string
  steps: Step[]
  sources: string[]
}
export type TicketDetail = { ticket: Ticket; conversation: LeadConversation | null }

export type AttentionItem = { id: string; severity: 'high' | 'medium' | 'low'; title: string; detail: string; link: string }
export type Briefing = {
  id: string
  period_days: number
  headline: string
  summary: string
  ai_written: boolean
  facts: Record<string, number | string>
  priorities: { item: AttentionItem; why: string }[]
  created_at: string
}
export type Attention = { facts: Record<string, number | string>; items: AttentionItem[] }

export type IntegrationView = {
  kind: 'email' | 'slack'
  config: Record<string, string | number | boolean>
  last_tested_at: string | null
  last_error: string | null
}
export type Integrations = { email: IntegrationView | null; slack: IntegrationView | null }

export type ChatSettings = { slug: string; enabled: boolean; welcome_message: string; sales_enabled: boolean; support_enabled: boolean }
export type InboxItem = {
  id: string
  mode: 'sales' | 'support' | 'test'
  customer_name: string | null
  customer_email: string | null
  state: 'ai' | 'needs_human' | 'human'
  waiting: boolean
  last_message: string
  last_message_role: string
  last_message_at: string
  message_count: number
  ticket_number: string | null
  lead_id: string | null
}
export type InboxDetail = {
  item: InboxItem
  channel: string
  escalation_reason: string | null
  can_reply: boolean
  ticket_id: string | null
  messages: ChatMessage[]
  email_status?: 'sent' | 'skipped_online' | 'skipped_recent' | 'no_email_setup' | 'no_customer_email' | 'failed' | null
}

export type OrderStatus = 'placed' | 'packed' | 'shipped' | 'out_for_delivery' | 'delivered' | 'cancelled' | 'returned'
export type Order = {
  id: string
  order_ref: string
  customer_name: string | null
  customer_email: string
  status: OrderStatus
  carrier: string | null
  tracking_id: string | null
  tracking_url: string | null
  items: { name: string; quantity: number }[]
  total: number | null
  currency: string
  placed_at: string | null
  expected_delivery: string | null
  updated_at: string
}

export type QueueItem = { kind: 'chat' | 'approval' | 'quote' | 'ticket' | 'lead'; urgency: 'high' | 'medium' | 'normal'; title: string; detail: string; to: string; action: string; at: string | null }
export type SetupStep = { key: string; title: string; hint: string; to: string; done: boolean; optional: boolean }
export type Today = {
  first_name: string
  business: string
  counts: { inbox: number; tickets: number; approvals: number }
  queue: QueueItem[]
  stats: { chats: number; leads: number; quotes_sent: number; tickets_resolved: number }
  steps: SetupStep[]
  chat_path: string | null
}
