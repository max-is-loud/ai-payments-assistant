import type { Escalation } from "../../api/types";
import { utcClock } from "../../lib/dates";
import type { EscalationState } from "../../state/useDashboard";
import { Button } from "../Button";
import { Eyebrow } from "../Eyebrow";
import { Figure } from "../Figure";

function sentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

function Action({ state, onApprove }: { state: EscalationState | "pending"; onApprove: () => void }) {
  switch (state) {
    case "notified":
      return <Button block size="lg" variant="secondary" disabled>Notified on Telegram</Button>;
    case "not-delivered":
      return <Button block size="lg" variant="secondary" disabled>Approved · Telegram not reached</Button>;
    case "approving":
      return <Button block size="lg" disabled>Approving…</Button>;
    default:
      return <Button block size="lg" onClick={onApprove}>Approve and notify</Button>;
  }
}

// The one bordered card in the rail — amber, because it is the only thing that
// needs the owner. The reason comes from the server; what approving does depends
// on whether there is an invoice to link to.
export function EscalationCard({ escalation, state, onApprove }: {
  escalation: Escalation;
  state: EscalationState | "pending";
  onApprove: () => void;
}) {
  const consequence = escalation.invoice_id
    ? "Approving sends them a Stripe payment link on Telegram."
    : "Approving tells them on Telegram that you will follow up.";
  return (
    <div className="ldg-card wait">
      <div className="head">
        <Eyebrow tone="wait">Waiting on you</Eyebrow>
        <span className="time">{utcClock(escalation.created_at)}</span>
      </div>
      <div className="headline">
        {escalation.amount_cents > 0 ? (
          <>{escalation.customer_name} wants to pay <Figure cents={escalation.amount_cents} size="sm" /></>
        ) : (
          <>{escalation.customer_name} needs you</>
        )}
      </div>
      <div className="body">{sentence(escalation.reason)} {consequence}</div>
      <Action state={state} onApprove={onApprove} />
    </div>
  );
}
