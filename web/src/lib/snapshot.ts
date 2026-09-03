// The last good dashboard numbers, kept in the browser so the next load paints
// them instantly while fresh data arrives, with the band saying how old they
// are. A snapshot is only reused on the day it was taken: yesterday's "taken
// today" must never pose as today's, even for six seconds.
import type { DailyFacts, SeriesResponse } from "../api/types";

const KEY = "ledger.dashboard";

export interface Snapshot {
  day: string;
  savedAt: number;
  facts: DailyFacts;
  currency: string;
  series: SeriesResponse | null;
}

export function saveSnapshot(storage: Storage, snapshot: Snapshot): void {
  try {
    storage.setItem(KEY, JSON.stringify(snapshot));
  } catch {
    /* quota exceeded or storage blocked: the next load is simply cold */
  }
}

export function loadSnapshot(storage: Storage, today: string): Snapshot | null {
  try {
    const raw = storage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Snapshot>;
    if (parsed.day !== today || !parsed.facts || typeof parsed.savedAt !== "number") return null;
    return {
      day: parsed.day, savedAt: parsed.savedAt, facts: parsed.facts,
      // A snapshot from before the field existed was taken on a dollar account.
      currency: parsed.currency ?? "usd",
      series: parsed.series ?? null,
    };
  } catch {
    return null;
  }
}
