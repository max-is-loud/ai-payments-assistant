import React from "react";
/** Ranked list with hairline tracks. rows: [{name, cents}] sorted desc. */
export function RankedBars({ rows = [] }) {
  const top = rows[0] ? rows[0].cents : 1;
  const fmt = (c) => "$" + Math.floor(c / 100).toLocaleString("en-US") + "." + String(c % 100).padStart(2, "0");
  return (
    <div className="ldg-ranked">
      {rows.map((r, i) => (
        <div className="row" key={i}>
          <span className="rank">{String(i + 1).padStart(2, "0")}</span>
          <div><div className="name">{r.name}</div><div className="track"><i style={{ width: (r.cents / top * 100).toFixed(0) + "%" }}></i></div></div>
          <span className="val">{fmt(r.cents)}</span>
        </div>
      ))}
    </div>
  );
}