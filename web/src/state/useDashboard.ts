import { useCallback, useEffect, useState } from "react";
import { apiFetch, describeError } from "../api/client";
import type { DailyFacts, Escalation, SeriesResponse, SummaryResponse } from "../api/types";

// Where an escalation card is in its click-through; absent means still pending.
export type EscalationState = "approving" | "notified" | "not-delivered";

const REFRESH_MS = 30_000;

// Everything on the page that is not the conversation: the narrated summary
// (fetched once), the facts and chart series (polled, no LLM), and the
// escalations. `onMutation` is the conversation's "money just moved" hook.
export function useDashboard(onMutation: (cb: () => void) => () => void) {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [facts, setFacts] = useState<DailyFacts | null>(null);
  const [series, setSeries] = useState<SeriesResponse | null>(null);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [escalationState, setEscalationState] = useState<Record<string, EscalationState>>({});
  const [railError, setRailError] = useState<string | null>(null);
  const [syncedAt, setSyncedAt] = useState<Date | null>(null);

  // Exact figures, no model call. Escalations are left alone right after an
  // approval so the card can show its outcome until the next poll clears it.
  const refresh = useCallback((withEscalations = true) => {
    const reads: Promise<unknown>[] = [
      apiFetch<SummaryResponse>("/api/summary/today?narrate=false").then((s) => setFacts(s.facts)),
      apiFetch<SeriesResponse>("/api/summary/series").then(setSeries),
    ];
    if (withEscalations) reads.push(apiFetch<Escalation[]>("/api/escalations").then(setEscalations));
    Promise.all(reads).then(() => setSyncedAt(new Date())).catch(() => undefined);
  }, []);

  useEffect(() => {
    apiFetch<SummaryResponse>("/api/summary/today")
      .then((s) => { setSummary(s); setFacts(s.facts); })
      .catch((e) => setSummaryError(describeError(e)));
    refresh();
    const unsubscribe = onMutation(refresh);
    const timer = setInterval(refresh, REFRESH_MS);
    return () => {
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

  return { summary, summaryError, facts, series, escalations, escalationState, railError, syncedAt, approveEscalation };
}
