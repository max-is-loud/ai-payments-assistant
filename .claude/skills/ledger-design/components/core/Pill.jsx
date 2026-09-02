import React from "react";
/** Status badge. tone: "neutral"|"in"|"out"|"wait"; solid drops the border (receipt status). */
export function Pill({ tone = "neutral", solid = false, children }) {
  return <span className={`ldg-pill ${tone === "neutral" ? "" : tone} ${solid ? "solid" : ""}`}>{children}</span>;
}