export type EventType = "planning" | "action" | "observation" | "confirmation" | "answer" | "clarify" | "error";

export interface AgentEvent {
  type: EventType;
  data: Record<string, unknown>;
}

// The figure and name the confirmation card leads with; absent when a pending
// proposal is restored after a reload, in which case the card shows the summary.
export interface ProposalDetails {
  amount_cents: number;
  counterparty: string | null;
  meta: string | null;
}

export interface Confirmation {
  action_id: string;
  action: string;
  summary: string;
  parameters: Record<string, unknown>;
  details?: ProposalDetails | null;
}

export interface PeriodTotals {
  label: string;
  succeeded_count: number;
  succeeded_total_cents: number;
  refunded_total_cents: number;
  declined_count: number;
  declined_reasons: Record<string, number>;
}

export interface OpenInvoiceFact {
  customer_name: string | null;
  number: string | null;
  amount_remaining_cents: number;
  due_date: string | null;
  overdue: boolean;
}

export interface DailyFacts {
  today: PeriodTotals;
  yesterday: PeriodTotals;
  open_invoices: OpenInvoiceFact[];
  open_invoice_total_cents: number;
  largest_payment: { customer_name: string | null; amount_cents: number; description: string | null } | null;
}

export interface SummaryResponse {
  facts: DailyFacts;
  text: string | null;
}

export interface Escalation {
  id: string;
  customer_name: string;
  invoice_id: string | null;
  amount_cents: number;
  reason: string;
  created_at: string;
}

export interface HistoryResponse {
  conversation_id: string;
  messages: { role: "user" | "assistant"; content: string; created_at: string }[];
  pending: Confirmation | null;
}

export interface ExecutedResult {
  action: string;
  data: Record<string, unknown>;
}

// GET /api/summary/series — the chart data, computed in Python, no LLM.
export interface DayTotals {
  date: string;
  succeeded_total_cents: number;
  succeeded_count: number;
}

export interface HourTotals {
  hour: number;
  succeeded_total_cents: number;
  succeeded_count: number;
}

export interface CustomerTotals {
  customer_name: string;
  succeeded_total_cents: number;
  succeeded_count: number;
}

export interface SeriesResponse {
  daily: DayTotals[];
  hourly_today: HourTotals[];
  top_customers: CustomerTotals[];
}
