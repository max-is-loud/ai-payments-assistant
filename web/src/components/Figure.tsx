import { splitUsd } from "../lib/money";

// A money figure in mono. `size` picks the type scale, `tone` colours it green
// for money in or coral for money out; money out is drawn with a true minus.
export function Figure({ cents, size = "md", tone = "", splitCents = false }: {
  cents: number;
  size?: "xl" | "lg" | "md" | "sm";
  tone?: "" | "in" | "out";
  splitCents?: boolean;
}) {
  const { dollars, cents: fraction } = splitUsd(Math.abs(cents));
  return (
    <span className={`ldg-figure ${size} ${tone}`}>
      {tone === "out" ? "−" : ""}
      {dollars}
      {splitCents ? <span className="cents">{fraction}</span> : fraction}
    </span>
  );
}
