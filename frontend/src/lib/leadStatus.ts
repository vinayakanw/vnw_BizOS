export const statusColor: Record<string, string> = {
  HOT: 'bg-red-100 text-red-700',
  WARM: 'bg-amber-100 text-amber-800',
  QUALIFYING: 'bg-sky-100 text-sky-800',
  NEW: 'bg-slate-100 text-slate-700',
  CONVERTED: 'bg-green-100 text-green-800',
  LOST: 'bg-slate-200 text-slate-500',
}

export const STATUSES = ['HOT', 'WARM', 'QUALIFYING', 'NEW', 'CONVERTED', 'LOST'] as const

export const actionColor: Record<string, string> = {
  executed: 'bg-green-100 text-green-800',
  pending_approval: 'bg-amber-100 text-amber-800',
  rejected: 'bg-slate-200 text-slate-600',
  failed: 'bg-red-100 text-red-700',
}

export const toolLabel: Record<string, string> = {
  create_quote: 'Quote',
  create_followup_task: 'Follow-up task',
  draft_email: 'Email draft',
  send_email: 'Email sent',
}

export const ticketStatusColor: Record<string, string> = {
  open: 'bg-red-100 text-red-700',
  in_progress: 'bg-amber-100 text-amber-800',
  resolved: 'bg-green-100 text-green-800',
}

export const priorityColor: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  normal: 'bg-slate-100 text-slate-700',
  low: 'bg-slate-50 text-slate-500',
}

export const inboxStateLabel: Record<string, { label: string; cls: string }> = {
  needs_human: { label: 'Needs a person', cls: 'bg-red-100 text-red-700' },
  human: { label: 'Team handling', cls: 'bg-emerald-100 text-emerald-800' },
  ai: { label: 'AI handling', cls: 'bg-slate-100 text-slate-600' },
}

export const quoteStatusLabel: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Draft, not sent', cls: 'bg-slate-100 text-slate-700' },
  sent: { label: 'Sent, waiting for the customer', cls: 'bg-sky-100 text-sky-800' },
  accepted: { label: 'Accepted by customer', cls: 'bg-green-100 text-green-800' },
  declined: { label: 'Declined by customer', cls: 'bg-slate-200 text-slate-600' },
  changes_requested: { label: 'Customer wants changes', cls: 'bg-amber-100 text-amber-800' },
}

export const orderStatusLabel: Record<string, { label: string; cls: string }> = {
  placed: { label: 'Placed', cls: 'bg-slate-100 text-slate-700' },
  packed: { label: 'Packed', cls: 'bg-sky-100 text-sky-800' },
  shipped: { label: 'Shipped', cls: 'bg-indigo-100 text-indigo-800' },
  out_for_delivery: { label: 'Out for delivery', cls: 'bg-amber-100 text-amber-800' },
  delivered: { label: 'Delivered', cls: 'bg-green-100 text-green-800' },
  cancelled: { label: 'Cancelled', cls: 'bg-slate-200 text-slate-600' },
  returned: { label: 'Returned', cls: 'bg-red-100 text-red-700' },
}

export const emailStatusText: Record<string, { text: string; cls: string }> = {
  sent: { text: 'The customer had left the chat, so they were also emailed your reply.', cls: 'text-green-700' },
  skipped_online: { text: 'The customer is on the page, so no email was needed.', cls: 'text-slate-500' },
  skipped_recent: { text: 'The customer was emailed a few minutes ago, so no second email was sent.', cls: 'text-slate-500' },
  no_email_setup: { text: 'The customer may have left, but email is not connected, so they will not be told. Connect it in Settings > Integrations.', cls: 'text-amber-700' },
  no_customer_email: { text: 'There is no email address for this customer.', cls: 'text-amber-700' },
  failed: { text: 'Your reply was saved, but the email to the customer failed. Check Settings > Integrations.', cls: 'text-red-600' },
}
