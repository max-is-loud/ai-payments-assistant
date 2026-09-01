import type { Escalation } from "../api/types";
import { formatUsd } from "../lib/money";

export function EscalationsPanel({ escalations, onApprove, busyId }: {
  escalations: Escalation[]; onApprove: (id: string) => void; busyId: string | null;
}) {
  return (
    <div className="card">
      <div className="eyebrow">Escalations</div>
      <h2>Waiting on you</h2>
      {escalations.length === 0 && <p className="empty">Nothing waiting. Customers above the bot's limit will appear here.</p>}
      {escalations.map((e) => (
        <div className="esc" key={e.id}>
          <div><strong>{e.customer_name}</strong> {e.amount_cents > 0 && <span className="amount">{formatUsd(e.amount_cents)}</span>}</div>
          <div className="meta">{e.reason} · {new Date(e.created_at + "Z").toLocaleString()}</div>
          <button className="btn primary" style={{ marginTop: 8 }} onClick={() => onApprove(e.id)} disabled={busyId === e.id}>
            {busyId === e.id ? "Approving…" : "Approve and notify"}
          </button>
        </div>
      ))}
    </div>
  );
}
