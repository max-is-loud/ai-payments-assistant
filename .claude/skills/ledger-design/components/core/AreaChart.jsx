import React from "react";
/** Full-width area trend. values: one number per day; the last point is "today" and gets the dot. Stroke stays 2px at any width. */
export function AreaChart({ values = [], height = 170, maxLabel }) {
  const W = 1000, pad = 12, max = Math.max(...values, 1);
  const pts = values.map((v, i) => [i / (values.length - 1) * W, height - pad - v / max * (height - pad * 2)]);
  const line = "M" + pts.map((p) => p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" L");
  const last = pts[pts.length - 1] || [W, height];
  return (
    <div className="ldg-area" style={{ height }}>
      <div className="grid"><i></i><i></i><i></i><i></i></div>
      {maxLabel && <div className="max">{maxLabel}</div>}
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
        <path className="fill" d={`${line} L${W} ${height} L0 ${height} Z`}></path>
        <path className="line" d={line}></path>
      </svg>
      <div className="today" style={{ top: (last[1] / height * 100).toFixed(1) + "%" }}></div>
    </div>
  );
}