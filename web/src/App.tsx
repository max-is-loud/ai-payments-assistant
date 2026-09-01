import { useConversation } from "./state/useConversation";
import { Composer } from "./components/Composer";
import { Trail } from "./components/Trail";
import { ConfirmationCard } from "./components/ConfirmationCard";
import { ResultCard } from "./components/ResultCard";

export default function App() {
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const { turns, busy, error, send, approve, cancel } = useConversation();
  return (
    <div className="shell">
      <header className="masthead">
        <h1 className="wordmark">Ledger <small>payments assistant</small></h1>
        <span className="dateline">{today}</span>
      </header>
      <main className="grid">
        <section aria-label="Conversation">
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
                  {t.text && <div className="bubble">{t.text}</div>}
                  {t.error && <div className="error">{t.error}</div>}
                </div>
              ),
            )}
            {error && <div className="error">{error}</div>}
          </div>
          <div style={{ height: 16 }} />
          <Composer onSend={send} disabled={busy} />
        </section>
        <aside className="rail" aria-label="Today and escalations" />
      </main>
    </div>
  );
}
