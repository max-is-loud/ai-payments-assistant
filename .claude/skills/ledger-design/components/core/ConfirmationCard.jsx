import React from "react";
import { AssistantBubble } from "./Bubble.jsx";
import { Eyebrow } from "./Eyebrow.jsx";
import { Figure } from "./Figure.jsx";
import { Button } from "./Button.jsx";
const VERB = { refund_payment: "Approve refund", create_invoice: "Create invoice", create_payment_link: "Create link", approve_escalation: "Approve and notify" };
/** Amber bubble that leads with the figure. decided: undefined | "approved" | "cancelled". */
export function ConfirmationCard({ action, amountCents, toName, meta, decided, busy, onApprove, onCancel, tone = "out" }) {
  return (
    <AssistantBubble tone="confirm">
      <Eyebrow tone="wait">Needs your approval</Eyebrow>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, margin: "6px 0 2px" }}>
        <Figure cents={amountCents} size="lg" tone={tone} sign={tone === "out" ? "−" : ""} />
        <span style={{ fontSize: 16 }}>to <strong>{toName}</strong></span>
      </div>
      {meta && <div style={{ color: "var(--ink-2)", fontSize: 14 }}>{meta}</div>}
      {decided ? <Eyebrow style={{ marginTop: 8 }}>{decided === "approved" ? "Approved" : "Cancelled"}</Eyebrow> : (
        <div className="actions">
          <Button onClick={onApprove} disabled={busy}>{VERB[action] || "Approve"}</Button>
          <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
        </div>
      )}
    </AssistantBubble>
  );
}