import { Composer } from "./components/Composer";
import { Hero } from "./components/Hero";
import { MastheadBand } from "./components/MastheadBand";
import { Rail } from "./components/rail/Rail";
import { Thread } from "./components/Thread";
import { TrendSection } from "./components/TrendSection";
import { useConversation } from "./state/useConversation";
import { CurrencyProvider } from "./state/useCurrency";
import { useDashboard } from "./state/useDashboard";
import { useTheme } from "./state/useTheme";

// One page: band, hero, trend, then the conversation beside the rail.
export default function App() {
  const { turns, busy, error, send, approve, cancel, onMutation } = useConversation();
  const dashboard = useDashboard(onMutation);
  const [theme, toggleTheme] = useTheme();
  return (
    <CurrencyProvider value={dashboard.currency}>
      <MastheadBand
        syncedAt={dashboard.syncedAt} syncError={dashboard.refreshError} onRetrySync={dashboard.retryRefresh}
        theme={theme} onToggleTheme={toggleTheme}
      />
      <div className="ldg-page">
        <Hero
          summary={dashboard.summary}
          loading={!dashboard.summary && !dashboard.summaryError}
          error={dashboard.summaryError}
          facts={dashboard.facts}
        />
        <TrendSection daily={dashboard.series?.daily ?? null} />
        <main className="ldg-main">
          <section aria-label="Conversation">
            <Thread turns={turns} busy={busy} error={error} onApprove={approve} onCancel={cancel} onRetry={send} />
            <div className="ldg-thread-gap" />
            <Composer onSend={send} disabled={busy} />
          </section>
          <Rail
            facts={dashboard.facts}
            series={dashboard.series}
            escalations={dashboard.escalations}
            escalationState={dashboard.escalationState}
            onApprove={dashboard.approveEscalation}
            error={dashboard.railError}
          />
        </main>
      </div>
    </CurrencyProvider>
  );
}
