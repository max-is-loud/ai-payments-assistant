import type { DailyFacts } from "../../api/types";
import { shortDate } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useCurrency } from "../../state/useCurrency";
import { RailSection } from "./RailSection";

// Open invoices, largest first, from the same facts the hero uses.
export function UnpaidSection({ facts }: { facts: DailyFacts | null }) {
  const currency = useCurrency();
  const title = facts ? <>Unpaid · {formatMoney(facts.open_invoice_total_cents, currency)}</> : "Unpaid";
  return (
    <RailSection title={title}>
      {!facts ? (
        <p className="ldg-empty">Loading…</p>
      ) : facts.open_invoices.length === 0 ? (
        <p className="ldg-empty">Nothing outstanding.</p>
      ) : (
        <div className="ldg-list">
          {facts.open_invoices.map((invoice) => (
            <div className="row" key={`${invoice.number}-${invoice.customer_name}-${invoice.amount_remaining_cents}`}>
              <span>
                {invoice.customer_name ?? "Customer"}
                {invoice.number && <span className="sub"> · {invoice.number}</span>}
                {invoice.due_date && (
                  <span className={invoice.overdue ? "sub out" : "sub"}>
                    {" · "}{invoice.overdue ? "overdue" : `due ${shortDate(invoice.due_date)}`}
                  </span>
                )}
              </span>
              <span className="ldg-mono">{formatMoney(invoice.amount_remaining_cents, currency)}</span>
            </div>
          ))}
        </div>
      )}
    </RailSection>
  );
}
