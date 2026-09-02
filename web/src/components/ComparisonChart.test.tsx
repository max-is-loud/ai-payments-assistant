// Two periods side by side: the later one in green, both on one scale so
// the bar heights can be compared across the gap.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ComparisonChart } from "./ComparisonChart";

const comparison = {
  earlier: { start: "2026-08-17", end: "2026-08-19", totalCents: 461000, count: 38, daily: [78000, 64000, 111000] },
  later: { start: "2026-08-24", end: "2026-08-26", totalCents: 528400, count: 41, daily: [91000, 118000, 0] },
};

describe("ComparisonChart", () => {
  it("labels both periods with human dates and marks the later one as the period of interest", () => {
    const { container } = render(<ComparisonChart comparison={comparison} />);
    const eyebrows = [...container.querySelectorAll(".ldg-eyebrow")];
    expect(eyebrows.map((e) => e.textContent)).toEqual(["Aug 17 – 19", "Aug 24 – 26"]);
    expect(eyebrows[1].className).toContain("in");
    expect([...container.querySelectorAll(".ldg-figure")].map((f) => f.textContent)).toEqual(["$4,610.00", "$5,284.00"]);
    expect([...container.querySelectorAll(".count")].map((c) => c.textContent)).toEqual(["· 38", "· 41"]);
  });

  it("draws one bar per day on a shared scale, with weekday initials underneath", () => {
    const { container } = render(<ComparisonChart comparison={comparison} />);
    const [earlier, later] = [...container.querySelectorAll(".ldg-bars")];
    expect(earlier.querySelectorAll("i")).toHaveLength(3);
    expect(later.querySelectorAll("i")).toHaveLength(3);
    expect([...later.querySelectorAll("i")].every((bar) => bar.className === "in")).toBe(true);
    const tallest = (group: Element) => Math.max(...[...group.querySelectorAll("i")].map((b) => parseFloat((b as HTMLElement).style.height)));
    expect(tallest(later)).toBe(100);
    expect(tallest(earlier)).toBeLessThan(100);
    expect([...container.querySelectorAll(".ldg-axis span")].map((s) => s.textContent)).toEqual(["M T W", "M T W"]);
  });
});
