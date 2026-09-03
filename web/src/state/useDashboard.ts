import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, describeError } from "../api/client";
import type { DailyFacts, Escalation, SeriesResponse, SummaryResponse } from "../api/types";
import { todayIso } from "../lib/dates";
import { loadSnapshot, saveSnapshot } from "../lib/snapshot";

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// Where an escalation card is in its click-through; absent means still pending.
export type EscalationState = "approving" | "notified" | "not-delivered";

const REFRESH_MS = 30_000;

// Everything on the page that is not the conversation: the narrated summary
// (fetched once), the facts and chart series (polled, no LLM), and the
// escalations. `onMutation` is the conversation's "money just moved" hook.
export function useDashboard(onMutation: (cb: () => void) => () => void) {
  // The last good numbers from earlier today paint at once, stamped with their
  // real age, while the fresh reads (one Stripe listing away) are in flight.
  const [snapshot] = useState(() => {
    const storage = browserStorage();
    return storage ? loadSnapshot(storage, todayIso()) : null;
  });
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [facts, setFacts] = useState<DailyFacts | null>(snapshot?.facts ?? null);
  const [currency, setCurrency] = useState<string>(snapshot?.currency ?? "usd");
  const [series, setSeries] = useState<SeriesResponse | null>(snapshot?.series ?? null);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [escalationState, setEscalationState] = useState<Record<string, EscalationState>>({});
  const [railError, setRailError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [syncedAt, setSyncedAt] = useState<Date | null>(snapshot ? new Date(snapshot.savedAt) : null);
  // The one narration request per page load; React's development StrictMode
  // runs the effect twice, and the second run must reuse this, not ask again.
  const narration = useRef<Promise<SummaryResponse> | null>(null);

  // Exact figures, no model call. Escalations are left alone right after an
  // approval so the card can show its outcome until the next poll clears it.
  // A failure is reported and leaves the figures and their time as they were:
  // "synced 3m ago" stays true, and nothing pretends to be fresher than it is.
  const refresh = useCallback((withEscalations = true): Promise<void> => {
    const facts$ = apiFetch<SummaryResponse>("/api/summary/today?narrate=false").then((s) => {
      setFacts(s.facts);
      setCurrency(s.currency);
      return s;
    });
    const series$ = apiFetch<SeriesResponse>("/api/summary/series").then((s) => {
      setSeries(s);
      return s;
    });
    const escalations$ = withEscalations
      ? apiFetch<Escalation[]>("/api/escalations").then(setEscalations)
      : Promise.resolve();
    return Promise.all([facts$, series$, escalations$])
      .then(([fresh, freshSeries]) => {
        const now = new Date();
        setSyncedAt(now);
        setRefreshError(null);
        const storage = browserStorage();
        if (storage) {
          saveSnapshot(storage, {
            day: todayIso(now), savedAt: now.getTime(),
            facts: fresh.facts, currency: fresh.currency, series: freshSeries,
          });
        }
      })
      .catch((e) => setRefreshError(describeError(e)));
  }, []);

  const retryRefresh = useCallback(() => refresh(), [refresh]);

  useEffect(() => {
    // The model writes a different narration each time it is asked, so the
    // cleaned-up mount's answer must not replace one already typing in, and
    // the second mount must not ask a second time.
    let cancelled = false;
    narration.current ??= apiFetch<SummaryResponse>("/api/summary/today");
    narration.current
      .then((s) => {
        if (cancelled) return;
        setSummary(s);
        setFacts(s.facts);
        setCurrency(s.currency);
      })
      .catch((e) => {
        narration.current = null;
        if (!cancelled) setSummaryError(describeError(e));
      });
    refresh();
    const unsubscribe = onMutation(refresh);
    const timer = setInterval(refresh, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
      unsubscribe();
    };
  }, [onMutation, refresh]);

  const approveEscalation = useCallback(async (id: string) => {
    setEscalationState((s) => ({ ...s, [id]: "approving" }));
    setRailError(null);
    try {
      const outcome = await apiFetch<{ notified: boolean }>(`/api/escalations/${id}/approve`, { method: "POST" });
      setEscalationState((s) => ({ ...s, [id]: outcome.notified ? "notified" : "not-delivered" }));
      refresh(false);
    } catch (e) {
      setEscalationState((s) => Object.fromEntries(Object.entries(s).filter(([key]) => key !== id)));
      setRailError(describeError(e));
    }
  }, [refresh]);

  return {
    summary, summaryError, facts, currency, series, escalations, escalationState, railError, syncedAt,
    refreshError, retryRefresh, approveEscalation,
  };
}
