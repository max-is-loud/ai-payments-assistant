import type { ExecutedResult } from "../api/types";
import { formatUsd } from "../lib/money";

export function ResultCard({ result }: { result: ExecutedResult }) {
  const d = result.data as Record<string, any>;
  switch (result.action) {
    case "refund_payment":
      return (
        <div className="result">
          <div className="eyebrow">Refund issued</div>
          <div className="big amount out">−{formatUsd(Number(d.amount_cents))}</div>
          <dl className="kv"><dt>To</dt><dd>{d.customer_name ?? "customer"}</dd><dt>Refund</dt><dd className="mono">{d.refund_id}</dd><dt>Status</dt><dd><span className="pill paid">{d.status}</span></dd></dl>
        </div>
      );
    case "create_invoice":
      return (
        <div className="result">
          <div className="eyebrow">Invoice created</div>
          <div className="big amount">{formatUsd(Number(d.total_cents))}</div>
          <dl className="kv"><dt>Customer</dt><dd>{d.customer_name}</dd><dt>Number</dt><dd className="mono">{d.number}</dd><dt>Due</dt><dd className="mono">{d.due_date}</dd><dt>Status</dt><dd><span className={`pill ${d.status}`}>{d.status}</span></dd>
          {d.hosted_url && <><dt>Link</dt><dd><a href={d.hosted_url} target="_blank" rel="noreferrer">Hosted invoice</a></dd></>}</dl>
        </div>
      );
    case "create_payment_link":
      return (
        <div className="result">
          <div className="eyebrow">Payment link</div>
          <div className="big amount">{formatUsd(Number(d.amount_cents))}</div>
          <dl className="kv"><dt>For</dt><dd>{d.description}</dd><dt>URL</dt><dd><a className="mono" href={d.url} target="_blank" rel="noreferrer">{d.url}</a></dd></dl>
        </div>
      );
    case "approve_escalation":
      return (
        <div className="result">
          <div className="eyebrow">Escalation approved</div>
          <dl className="kv"><dt>Customer</dt><dd>{d.customer_name}</dd><dt>Amount</dt><dd className="amount">{formatUsd(Number(d.amount_cents))}</dd><dt>Telegram</dt><dd><span className={`pill ${d.notified ? "paid" : "failed"}`}>{d.notified ? "notified" : "not delivered"}</span></dd></dl>
        </div>
      );
    default:
      return <pre className="result mono">{JSON.stringify(d, null, 2)}</pre>;
  }
}
