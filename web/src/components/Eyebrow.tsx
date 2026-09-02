import type { ReactNode } from "react";

// Mono uppercase label above every block. Green for money in, amber for
// anything waiting on the owner, coral for money out or an error.
export function Eyebrow({ tone = "", className = "", children }: {
  tone?: "" | "in" | "wait" | "out";
  className?: string;
  children: ReactNode;
}) {
  return <div className={["ldg-eyebrow", tone, className].filter(Boolean).join(" ")}>{children}</div>;
}
