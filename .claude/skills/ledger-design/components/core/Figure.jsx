import React from "react";
/** A money figure in mono. Cents are dimmed on xl. size: "xl"|"lg"|"md"|"sm"; tone: ""|"in"|"out" */
export function Figure({ cents, size = "md", tone = "", sign = "", splitCents = false }) {
  const abs = Math.abs(cents);
  const dollars = "$" + Math.floor(abs / 100).toLocaleString("en-US");
  const cc = "." + String(abs % 100).padStart(2, "0");
  return (
    <span className={`ldg-figure ${size} ${tone}`}>
      {sign}{dollars}{splitCents ? <span className="cents">{cc}</span> : cc}
    </span>
  );
}