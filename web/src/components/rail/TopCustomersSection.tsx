import type { CustomerTotals } from "../../api/types";
import { RankedBars } from "../charts/RankedBars";
import { RailSection } from "./RailSection";

export function TopCustomersSection({ customers }: { customers: CustomerTotals[] | null }) {
  return (
    <RailSection title="Top customers · 3 weeks">
      {customers === null ? (
        <p className="ldg-empty">Loading…</p>
      ) : customers.length === 0 ? (
        <p className="ldg-empty">No payments in the last three weeks.</p>
      ) : (
        <RankedBars rows={customers.map((c) => ({ name: c.customer_name, cents: c.succeeded_total_cents }))} />
      )}
    </RailSection>
  );
}
