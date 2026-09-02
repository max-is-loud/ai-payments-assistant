import { useCallback, useEffect, useState } from "react";
import { useConversation } from "./state/useConversation";
import { Composer } from "./components/Composer";
import { Trail } from "./components/Trail";
import { ConfirmationCard } from "./components/ConfirmationCard";
import { ResultCard } from "./components/ResultCard";
import { ApiError, apiFetch } from "./api/client";
import type { DailyFacts, Escalation, SummaryResponse } from "./api/types";
import { SummaryCard } from "./components/SummaryCard";
import { TodayRail } from "./components/TodayRail";
import { EscalationsPanel } from "./components/EscalationsPanel";
import { Markdown } from "./components/Markdown";

export default function App() {
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const { turns, busy, error, send, approve, cancel, onMutation } = useConversation();
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [facts, setFacts] = useState<DailyFacts | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [approving, setApproving] = useState<string | null>(null);

  const refreshFacts = useCallback(() => {
    apiFetch<SummaryResponse>("/api/summary/today?narrate=false").then((s) => setFacts(s.facts)).catch(() => undefined);
    apiFetch<Escalation[]>("/api/escalations").then(setEscalations).catch(() => undefined);
  }, []);

  useEffect(() => {
    apiFetch<SummaryResponse>("/api/summary/today")
      .then((s) => { setSummary(s); setFacts(s.facts); })
      .catch((e) => setSummaryError(e instanceof ApiError && e.hint ? `${e.message} ${e.hint}` : String(e)));
    apiFetch<Escalation[]>("/api/escalations").then(setEscalations).catch(() => undefined);
    const unsubscribe = onMutation(refreshFacts);
    const timer = setInterval(refreshFacts, 30_000);
    return () => {
      clearInterval(timer);
      unsubscribe();
    };
  }, [onMutation, refreshFacts]);

  const approveEscalation = async (id: string) => {
    setApproving(id);
    try { await apiFetch(`/api/escalations/${id}/approve`, { method: "POST" }); refreshFacts(); }
    finally { setApproving(null); }
  };

  return (
    <div className="shell">
      <header className="masthead">
        <h1 className="wordmark">Ledger <small>payments assistant</small></h1>
        <span className="dateline">{today}</span>
      </header>
      <main className="grid">
        <section aria-label="Conversation">
          <SummaryCard summary={summary} loading={!summary && !summaryError} error={summaryError} />
          <div className="thread">
            {turns.length === 0 && <p className="empty">Ask me to refund, invoice, or summarise.</p>}
            {turns.map((t) =>
              t.role === "user" ? (
                <div key={t.id} className="turn user">{t.text}</div>
              ) : (
                <div key={t.id} className="turn assistant">
                  <Trail events={t.events} />
                  {t.confirmation && (
                    <ConfirmationCard confirmation={t.confirmation} decided={t.decided} busy={busy}
                      onApprove={() => approve(t.confirmation!.action_id)} onCancel={() => cancel(t.confirmation!.action_id)} />
                  )}
                  {t.result && <ResultCard result={t.result} />}
                  {t.text && <div className="bubble"><Markdown>{t.text}</Markdown></div>}
                  {t.error && <div className="error">{t.error}</div>}
                </div>
              ),
            )}
            {error && <div className="error">{error}</div>}
          </div>
          <div style={{ height: 16 }} />
          <Composer onSend={send} disabled={busy} />
        </section>
        <aside className="rail" aria-label="Today and escalations">
          <TodayRail facts={facts} />
          <EscalationsPanel escalations={escalations} onApprove={approveEscalation} busyId={approving} />
        </aside>
      </main>
    </div>
  );
}
