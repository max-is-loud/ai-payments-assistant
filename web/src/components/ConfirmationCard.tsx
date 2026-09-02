import type { Confirmation } from "../api/types";
import { AssistantBubble } from "./Bubbles";
import { Button } from "./Button";
import { Eyebrow } from "./Eyebrow";
import { Figure } from "./Figure";

const VERB: Record<string, string> = {
  refund_payment: "Approve refund", create_invoice: "Create invoice", create_payment_link: "Create link",
  approve_escalation: "Approve and notify",
};

// Money leaves on a refund; every other proposal asks for money to come in.
const PREPOSITION: Record<string, string> = { refund_payment: "to", create_invoice: "for", approve_escalation: "for" };

// The amber bubble. It leads with the figure and the name when the server sent
// them; a proposal restored after a reload has only its sentence, which still reads.
export function ConfirmationCard({ confirmation, decided, busy, onApprove, onCancel }: {
  confirmation: Confirmation;
  decided?: "approved" | "cancelled";
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const { action, summary, details } = confirmation;
  return (
    <AssistantBubble tone="confirm" role="group" aria-label="Confirmation">
      <Eyebrow tone="wait">Needs your approval</Eyebrow>
      {details ? (
        <>
          <div className="ldg-confirm-row">
            <Figure cents={details.amount_cents} size="lg" tone={action === "refund_payment" ? "out" : ""} />
            {details.counterparty && (
              <span className="to">{PREPOSITION[action] ?? "for"} <strong>{details.counterparty}</strong></span>
            )}
          </div>
          {details.meta && <div className="ldg-meta">{details.meta}</div>}
        </>
      ) : (
        <p>{summary}</p>
      )}
      {decided ? (
        <Eyebrow className="decided">{decided === "approved" ? "Approved" : "Cancelled"}</Eyebrow>
      ) : (
        <div className="actions">
          <Button onClick={onApprove} disabled={busy}>{VERB[action] ?? "Approve"}</Button>
          <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
        </div>
      )}
    </AssistantBubble>
  );
}
