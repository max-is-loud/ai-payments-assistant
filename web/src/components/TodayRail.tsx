import type { DailyFacts } from "../api/types";
import { formatUsd } from "../lib/money";

export function TodayRail({ facts }: { facts: DailyFacts | null }) {
  if (!facts) return <div className="card"><div className="eyebrow">Today</div><p className="empty">Loading…</p></div>;
  const declined = Object.entries(facts.today.declined_reasons).map(([r, n]) => `${n} ${r.replace(/_/g, " ")}`).join(", ");
  return (
    <div className="card">
      <div className="eyebrow">Today · {facts.today.label}</div>
      <div className="stat"><span className="label">Taken</span><span className="amount in">{formatUsd(facts.today.succeeded_total_cents)}</span></div>
      <div className="stat"><span className="label">Payments</span><span className="mono">{facts.today.succeeded_count}</span></div>
      <div className="stat"><span className="label">Refunded</span><span className="amount out">{formatUsd(facts.today.refunded_total_cents)}</span></div>
      <div className="stat"><span className="label">Declined</span><span className="mono" title={declined}>{facts.today.declined_count}</span></div>
      <div className="stat"><span className="label">Yesterday</span><span className="amount">{formatUsd(facts.yesterday.succeeded_total_cents)}</span></div>
      <div className="stat"><span className="label">Unpaid invoices</span><span className="amount">{formatUsd(facts.open_invoice_total_cents)}</span></div>
    </div>
  );
}
