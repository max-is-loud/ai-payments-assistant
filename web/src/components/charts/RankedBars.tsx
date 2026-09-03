import { formatMoney } from "../../lib/money";
import { useCurrency } from "../../state/useCurrency";

// Ranked list with a 3px track under each name, sized as a share of the leader.
export function RankedBars({ rows }: { rows: { name: string; cents: number }[] }) {
  const currency = useCurrency();
  const top = rows[0]?.cents || 1;
  return (
    <div className="ldg-ranked">
      {rows.map((row, i) => (
        <div className="row" key={row.name}>
          <span className="rank">{String(i + 1).padStart(2, "0")}</span>
          <div>
            <div className="name">{row.name}</div>
            <div className="track"><i style={{ width: `${((row.cents / top) * 100).toFixed(0)}%` }} /></div>
          </div>
          <span className="val">{formatMoney(row.cents, currency)}</span>
        </div>
      ))}
    </div>
  );
}
