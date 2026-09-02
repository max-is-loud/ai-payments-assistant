import React from "react";
/** Mono uppercase label. tone: "" | "in" | "wait" | "out" */
export function Eyebrow({ tone = "", children, style }) {
  return <div className={"ldg-eyebrow " + tone} style={style}>{children}</div>;
}