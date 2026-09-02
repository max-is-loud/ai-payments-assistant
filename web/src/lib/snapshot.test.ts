// The last good dashboard numbers are kept in the browser so the next load
// paints instantly and honestly ("synced 3m ago") while fresh data arrives.
// Yesterday's numbers must never pose as today's.
import { describe, expect, it } from "vitest";
import type { DailyFacts, SeriesResponse } from "../api/types";
import { loadSnapshot, saveSnapshot, type Snapshot } from "./snapshot";

class MemoryStorage implements Storage {
  private map = new Map<string, string>();
  get length() { return this.map.size; }
  clear() { this.map.clear(); }
  getItem(key: string) { return this.map.get(key) ?? null; }
  key(index: number) { return [...this.map.keys()][index] ?? null; }
  removeItem(key: string) { this.map.delete(key); }
  setItem(key: string, value: string) { this.map.set(key, value); }
}

const facts = {
  today: { label: "2026-09-02", succeeded_count: 18, succeeded_total_cents: 257800, refunded_total_cents: 0, declined_count: 2, declined_reasons: { insufficient_funds: 2 } },
  yesterday: { label: "2026-09-01", succeeded_count: 19, succeeded_total_cents: 280900, refunded_total_cents: 4400, declined_count: 2, declined_reasons: {} },
  open_invoices: [], open_invoice_total_cents: 378000, largest_payment: null,
} as DailyFacts;

const series = { daily: [], hourly_today: [], top_customers: [] } as SeriesResponse;

const snapshot: Snapshot = { day: "2026-09-02", savedAt: 1_700_000_000_000, facts, series };

describe("snapshot", () => {
  it("round-trips the numbers saved earlier the same day", () => {
    const storage = new MemoryStorage();
    saveSnapshot(storage, snapshot);
    expect(loadSnapshot(storage, "2026-09-02")).toEqual(snapshot);
  });

  it("refuses a snapshot from another day, so yesterday's figure never poses as today's", () => {
    const storage = new MemoryStorage();
    saveSnapshot(storage, snapshot);
    expect(loadSnapshot(storage, "2026-09-03")).toBeNull();
  });

  it("treats a missing or unreadable entry as a cold start", () => {
    const storage = new MemoryStorage();
    expect(loadSnapshot(storage, "2026-09-02")).toBeNull();
    storage.setItem("ledger.dashboard", "{not json");
    expect(loadSnapshot(storage, "2026-09-02")).toBeNull();
  });

  it("never throws when storage is unavailable", () => {
    const broken = {
      getItem: () => { throw new Error("blocked"); },
      setItem: () => { throw new Error("quota"); },
    } as unknown as Storage;
    expect(() => saveSnapshot(broken, snapshot)).not.toThrow();
    expect(loadSnapshot(broken, "2026-09-02")).toBeNull();
  });
});
