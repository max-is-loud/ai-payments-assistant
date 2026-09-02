import type { ReactNode } from "react";
import type { ExecutedResult } from "../api/types";
import { shortDate } from "../lib/dates";
import { AssistantBubble } from "./Bubbles";
import { Figure } from "./Figure";
import { Pill } from "./Pill";

type StatusTone = "in" | "out" | "wait" | "neutral";

interface Receipt {
  title: string;
  cents: number;
  tone: "" | "in" | "out";
  description: ReactNode;
  status: string;
  statusTone: StatusTone;
}

const INVOICE_STATUS: Record<string, StatusTone> = {
  paid: "in", open: "wait", draft: "neutral", void: "out", uncollectible: "out",
};

// Each handler's return value, read into the receipt's three columns.
function receipt(result: ExecutedResult): Receipt | null {
  const data = result.data;
  const text = (key: string) => (data[key] == null ? "" : String(data[key]));
  switch (result.action) {
    case "refund_payment":
      return {
        title: "Refund issued", cents: Number(data.amount_cents), tone: "out",
        description: <>to {text("customer_name") || "customer"} · <span className="ldg-mono">{text("refund_id")}</span></>,
        status: text("status"), statusTone: data.status === "succeeded" ? "in" : "wait",
      };
    case "create_invoice":
      return {
        title: "Invoice created", cents: Number(data.total_cents), tone: "",
        description: (
          <>
            {text("customer_name")} · <span className="ldg-mono">{text("number")}</span>
            {data.due_date ? ` · due ${shortDate(text("due_date"))}` : ""}
            {data.hosted_url ? <> · <a href={text("hosted_url")} target="_blank" rel="noreferrer">Hosted invoice</a></> : null}
          </>
        ),
        status: text("status"), statusTone: INVOICE_STATUS[text("status")] ?? "neutral",
      };
    case "create_payment_link":
      return {
        title: "Payment link created", cents: Number(data.amount_cents), tone: "",
        description: <>{text("description")} · <a className="ldg-mono" href={text("url")} target="_blank" rel="noreferrer">{text("url")}</a></>,
        status: "ready", statusTone: "in",
      };
    case "approve_escalation":
      return {
        title: "Escalation approved", cents: Number(data.amount_cents), tone: "",
        description: <>{text("customer_name")}{data.already_approved ? " · already approved" : ""}</>,
        status: data.notified ? "notified" : "not delivered", statusTone: data.notified ? "in" : "out",
      };
    default:
      return null;
  }
}

// Three columns — figure, description, status pill — under a green dotted eyebrow.
export function ReceiptCard({ result }: { result: ExecutedResult }) {
  const shaped = receipt(result);
  if (!shaped) {
    return <AssistantBubble><pre className="ldg-mono">{JSON.stringify(result.data, null, 2)}</pre></AssistantBubble>;
  }
  return (
    <AssistantBubble>
      <div className="ldg-receipt">
        <div className="head ldg-eyebrow in"><i className="ldg-dot" />{shaped.title}</div>
        <Figure cents={shaped.cents} size="lg" tone={shaped.tone} />
        <div className="desc">{shaped.description}</div>
        <Pill tone={shaped.statusTone} solid>{shaped.status}</Pill>
      </div>
    </AssistantBubble>
  );
}
