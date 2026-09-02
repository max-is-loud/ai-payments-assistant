import React from "react";
import { AssistantBubble } from "./Bubble.jsx";
import { Figure } from "./Figure.jsx";
import { Pill } from "./Pill.jsx";
/** Three-column receipt: figure · description · status pill, with a green dotted eyebrow. */
export function ReceiptCard({ title, amountCents, tone = "out", description, status, statusTone = "in" }) {
  return (
    <AssistantBubble>
      <div className="ldg-receipt">
        <div className="head ldg-eyebrow in"><i className="ldg-dot"></i>{title}</div>
        <Figure cents={amountCents} size="lg" tone={tone} sign={tone === "out" ? "−" : ""} />
        <div style={{ fontSize: 14, color: "var(--ink-2)" }}>{description}</div>
        <Pill tone={statusTone} solid>{status}</Pill>
      </div>
    </AssistantBubble>
  );
}