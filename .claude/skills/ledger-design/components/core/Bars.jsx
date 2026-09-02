import React from "react";
/** Mini bar chart. values: number[]; max defaults to the largest value; tone: ""(muted) | "in" | "ink"; size: "" | "sm" | "rail". Bars are 2px minimum so zero-days still read. */
export function Bars({ values = [], max, tone = "", size = "", height, titles = [] }) {
  const m = max || Math.max(...values, 1);
  const h = height || (size === "sm" ? 48 : 56);
  return (
    <div className={`ldg-bars ${size}`} style={height ? { height } : undefined}>
      {values.map((v, i) => <i key={i} className={tone} title={titles[i]} style={{ height: Math.max(2, Math.round(v / m * h)) }}></i>)}
    </div>
  );
}
/** Axis row under a chart. labels: string[]; the last label may be highlighted with tone "in". */
export function Axis({ labels = [], lastTone = "", xs = false }) {
  return <div className={"ldg-axis " + (xs ? "xs" : "")}>{labels.map((l, i) => <span key={i} className={i === labels.length - 1 ? lastTone : ""}>{l}</span>)}</div>;
}