// An answer that compares two periods gets a chart drawn from the two
// query_payments observations already in the turn — no second request.
import { describe, expect, it } from "vitest";
import type { AgentEvent } from "../api/types";
import { findComparison } from "./comparison";

const day = (date: string, cents: number) => ({ date, succeeded_total_cents: cents, succeeded_count: cents ? 1 : 0 });

const observation = (name: string, result: Record<string, unknown>): AgentEvent => ({
  type: "observation",
  data: { name, result },
});

const lastWeek = observation("query_payments", {
  period: "2026-08-24 to 2026-08-26",
  succeeded_total_cents: 5284_00,
  succeeded_count: 41,
  daily_totals: [day("2026-08-24", 910_00), day("2026-08-25", 1180_00), day("2026-08-26", 0)],
});

const weekBefore = observation("query_payments", {
  period: "2026-08-17 to 2026-08-19",
  succeeded_total_cents: 4610_00,
  succeeded_count: 38,
  daily_totals: [day("2026-08-17", 780_00), day("2026-08-18", 640_00), day("2026-08-19", 1110_00)],
});

describe("findComparison", () => {
  it("pairs two ranged queries with the earlier period first, whatever order they ran in", () => {
    const events: AgentEvent[] = [
      { type: "planning", data: { reasoning: "Compare the weeks." } },
      lastWeek,
      weekBefore,
    ];
    expect(findComparison(events)).toEqual({
      earlier: {
        start: "2026-08-17", end: "2026-08-19", totalCents: 4610_00, count: 38,
        daily: [780_00, 640_00, 1110_00],
      },
      later: {
        start: "2026-08-24", end: "2026-08-26", totalCents: 5284_00, count: 41,
        daily: [910_00, 1180_00, 0],
      },
    });
  });

  it("needs two ranged queries: one query, or an unbounded one, draws nothing", () => {
    expect(findComparison([lastWeek])).toBeNull();
    const allTime = observation("query_payments", { period: "all time", succeeded_total_cents: 1, succeeded_count: 1 });
    expect(findComparison([lastWeek, allTime])).toBeNull();
  });

  it("ignores failed observations and other actions", () => {
    const failed = observation("query_payments", { error: "Stripe rejected the request." });
    const other = observation("find_customer", { count: 1, daily_totals: [] });
    expect(findComparison([failed, other, lastWeek])).toBeNull();
  });
});
