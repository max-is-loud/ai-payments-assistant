import React from "react";
import { Eyebrow } from "./Eyebrow.jsx";
import { Figure } from "./Figure.jsx";
import { Button } from "./Button.jsx";
/** The one card in the rail that has a border — amber, because it waits on the owner. */
export function EscalationCard({ customerName, amountCents, time, reason = "At or above the bot's $2,000 limit. Approving sends them a Stripe payment link on Telegram.", busy, onApprove }) {
  return (
    <div className="ldg-card wait">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}><Eyebrow tone="wait">Waiting on you</Eyebrow><span className="ldg-mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{time}</span></div>
      <div className="headline">{customerName} wants to pay <Figure cents={amountCents} size="sm" /></div>
      <div style={{ color: "var(--ink-2)", fontSize: 14, marginBottom: 12 }}>{reason}</div>
      <Button block size="lg" disabled={busy} onClick={onApprove}>{busy ? "Approving…" : "Approve and notify"}</Button>
    </div>
  );
}