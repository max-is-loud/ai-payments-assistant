import { longDate, relativeAgo } from "../lib/dates";
import type { Theme } from "../state/useTheme";
import { useTicker } from "../state/useTicker";
import { Button } from "./Button";

// Full-width ink band: wordmark and tag left; sync status, date, and the theme
// toggle right. "Stripe test mode" is a fact, not a label — the API refuses live keys.
export function MastheadBand({ syncedAt, theme, onToggleTheme }: {
  syncedAt: Date | null;
  theme: Theme;
  onToggleTheme: () => void;
}) {
  const now = useTicker(5_000);
  const status = syncedAt ? `Stripe test mode · synced ${relativeAgo(syncedAt, now)}` : "Stripe test mode · syncing…";
  return (
    <header className="ldg-band">
      <div className="brand">
        <span className="wordmark">Ledger</span>
        <span className="tag">payments assistant</span>
      </div>
      <div className="meta">
        <span><i className="ldg-dot" />{status}</span>
        <span>{longDate(now)}</span>
        <Button variant="secondary" onClick={onToggleTheme} aria-label="Switch theme">
          {theme === "dark" ? "Light" : "Dark"}
        </Button>
      </div>
    </header>
  );
}
