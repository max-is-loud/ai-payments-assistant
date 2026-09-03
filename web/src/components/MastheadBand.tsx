import { longDate, relativeAgo } from "../lib/dates";
import type { Theme } from "../state/useTheme";
import { useTicker } from "../state/useTicker";
import { Button } from "./Button";

// Full-width ink band: wordmark and tag left; sync status, date, and the theme
// toggle right. "Stripe test mode" is a fact, not a label — the API refuses live
// keys. A failed refresh is said out loud, with the age of the figures still on
// the page and a way to try again; the figures themselves stay where they are.
export function MastheadBand({ syncedAt, syncError, onRetrySync, theme, onToggleTheme }: {
  syncedAt: Date | null;
  syncError: string | null;
  onRetrySync: () => void;
  theme: Theme;
  onToggleTheme: () => void;
}) {
  const now = useTicker(5_000);
  const age = syncedAt ? relativeAgo(syncedAt, now) : null;
  const status = syncError
    ? `Stripe test mode · sync failed${age ? `, showing figures from ${age}` : ""}`
    : age ? `Stripe test mode · synced ${age}` : "Stripe test mode · syncing…";
  return (
    <header className="ldg-band">
      <div className="brand">
        <span className="wordmark">Ledger</span>
        <span className="tag">payments assistant</span>
      </div>
      <div className="meta">
        <span title={syncError ?? undefined}><i className="ldg-dot" />{status}</span>
        {syncError && <Button variant="danger" onClick={onRetrySync}>Retry</Button>}
        <span>{longDate(now)}</span>
        <Button variant="secondary" onClick={onToggleTheme} aria-label="Switch theme">
          {theme === "dark" ? "Light" : "Dark"}
        </Button>
      </div>
    </header>
  );
}
