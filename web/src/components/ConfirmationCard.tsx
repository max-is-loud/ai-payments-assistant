import type { Confirmation } from "../api/types";

const VERB: Record<string, string> = {
  refund_payment: "Approve refund", create_invoice: "Create invoice", create_payment_link: "Create link",
  approve_escalation: "Approve and notify",
};

export function ConfirmationCard({ confirmation, decided, busy, onApprove, onCancel }: {
  confirmation: Confirmation; decided?: "approved" | "cancelled"; busy: boolean;
  onApprove: () => void; onCancel: () => void;
}) {
  return (
    <div className="confirm" role="group" aria-label="Confirmation">
      <div className="eyebrow">Needs your approval</div>
      <div>{confirmation.summary}</div>
      {decided ? (
        <div className="eyebrow" style={{ marginTop: 8 }}>{decided === "approved" ? "Approved" : "Cancelled"}</div>
      ) : (
        <div className="actions">
          <button className="btn primary" onClick={onApprove} disabled={busy}>{VERB[confirmation.action] ?? "Approve"}</button>
          <button className="btn" onClick={onCancel} disabled={busy}>Cancel</button>
        </div>
      )}
    </div>
  );
}
