import type { SummaryResponse } from "../api/types";
import { Markdown } from "./Markdown";

export function SummaryCard({ summary, loading, error }: { summary: SummaryResponse | null; loading: boolean; error: string | null }) {
  return (
    <div className="card" aria-live="polite">
      <div className="eyebrow">Today, in a sentence</div>
      <h2>Good {new Date().getHours() < 12 ? "morning" : "afternoon"}.</h2>
      {loading && <p className="empty">Reading today's activity…</p>}
      {error && <p className="error">{error}</p>}
      {summary?.text && <div className="lede"><Markdown>{summary.text}</Markdown></div>}
    </div>
  );
}
