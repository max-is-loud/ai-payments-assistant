import type { ReactNode } from "react";

// Status badge. `solid` drops the border for a receipt's final status.
export function Pill({ tone = "neutral", solid = false, children }: {
  tone?: "neutral" | "in" | "out" | "wait";
  solid?: boolean;
  children: ReactNode;
}) {
  const cls = ["ldg-pill", tone === "neutral" ? "" : tone, solid ? "solid" : ""].filter(Boolean).join(" ");
  return <span className={cls}>{children}</span>;
}
