// The hero speaks first: a blinking cursor holds the aside's place while the
// narrator works, then the aside and the lede type in, and the day's figure
// with its pills is computed from facts, not prose.
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

const text = "A strong Wednesday.\n\nYou took **$2,412.00** across 18 payments today.";

describe("Hero", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("holds the aside's place with a cursor while the summary is still being written", () => {
    const { container } = render(<Hero summary={null} loading error={null} facts={null} />);
    expect(container.querySelector("h1 .ldg-cursor")).not.toBeNull();
    expect(container.querySelector(".ldg-lede")).toBeNull();
  });

  it("types the aside first, then the lede, and puts the cursor away when both are done", () => {
    const { container } = render(<Hero summary={{ facts, text }} loading={false} error={null} facts={facts} />);
    act(() => vi.advanceTimersByTime(200));
    const partial = container.querySelector("h1 em")?.textContent ?? "";
    expect(partial.length).toBeGreaterThan(0);
    expect(partial.length).toBeLessThan("A strong Wednesday.".length);
    expect(container.querySelector("h1 .ldg-cursor")).not.toBeNull();
    expect(container.querySelector(".ldg-lede")).toBeNull();

    // One act per frame the browser would render: the aside finishes, the lede starts, the lede finishes.
    act(() => vi.advanceTimersByTime(400));
    act(() => vi.advanceTimersByTime(2000));
    expect(container.querySelector("h1 em")?.textContent).toBe("A strong Wednesday.");
    expect(container.querySelector(".ldg-lede strong")?.textContent).toBe("$2,412.00");
    expect(container.querySelector(".ldg-cursor")).toBeNull();
    expect(container.querySelector(".ldg-lede")?.textContent).not.toContain("A strong Wednesday.");
  });

  it("keeps bold intact while the lede is mid-reveal", () => {
    const { container } = render(<Hero summary={{ facts, text }} loading={false} error={null} facts={facts} />);
    act(() => vi.advanceTimersByTime(600));
    act(() => vi.advanceTimersByTime(700));
    const lede = container.querySelector(".ldg-lede");
    expect(lede).not.toBeNull();
    const revealed = lede?.textContent ?? "";
    expect(revealed.length).toBeGreaterThan(0);
    expect(revealed.length).toBeLessThan("You took $2,412.00 across 18 payments today.".length);
    expect(revealed).not.toContain("**");
    expect(lede?.querySelector(".ldg-cursor")).not.toBeNull();
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
});
