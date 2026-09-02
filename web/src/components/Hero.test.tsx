// The hero speaks first: the narrator's aside in the serif, the lede as
// Markdown, and the day's figure with pills computed from facts, not prose.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DailyFacts, PeriodTotals } from "../api/types";
import { Hero } from "./Hero";

const period = (cents: number, count: number, declined = 0): PeriodTotals => ({
  label: "2026-09-02", succeeded_count: count, succeeded_total_cents: cents, refunded_total_cents: 0,
  declined_count: declined, declined_reasons: declined ? { insufficient_funds: declined } : {},
});

const facts: DailyFacts = {
  today: period(241200, 18, 2), yesterday: period(133600, 11),
  open_invoices: [], open_invoice_total_cents: 0, largest_payment: null,
};

describe("Hero", () => {
  it("lifts the narrator's aside into the greeting and renders the lede as Markdown", () => {
    const text = "A strong Wednesday.\n\nYou took **$2,412.00** across 18 payments today.";
    const { container } = render(<Hero summary={{ facts, text }} loading={false} error={null} facts={facts} />);
    expect(container.querySelector("h1 em")?.textContent).toBe("A strong Wednesday.");
    expect(container.querySelector(".ldg-lede strong")?.textContent).toBe("$2,412.00");
    expect(container.querySelector(".ldg-lede")?.textContent).not.toContain("A strong Wednesday.");
  });

  it("shows today's figure with the change, the count, and the declines as pills", () => {
    const { container } = render(<Hero summary={null} loading={false} error={null} facts={facts} />);
    expect(container.querySelector(".ldg-figure.xl")?.textContent).toBe("$2,412.00");
    expect([...container.querySelectorAll(".ldg-pill")].map((p) => p.textContent)).toEqual([
      "+80.5% vs yesterday", "18 payments", "2 declined",
    ]);
  });

  it("drops pills it cannot say: no comparison without a yesterday, no declines when none", () => {
    const quiet: DailyFacts = { ...facts, today: period(5000, 1), yesterday: period(0, 0) };
    const { container } = render(<Hero summary={null} loading={false} error={null} facts={quiet} />);
    expect([...container.querySelectorAll(".ldg-pill")].map((p) => p.textContent)).toEqual(["1 payment"]);
  });

  it("says it is reading while the summary loads", () => {
    const { container } = render(<Hero summary={null} loading error={null} facts={null} />);
    expect(container.querySelector(".ldg-empty")?.textContent).toBe("Reading today's activity…");
  });
});
