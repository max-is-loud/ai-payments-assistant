import type { SummaryResponse } from "../api/types";

export function SummaryCard({ summary, loading, error }: { summary: SummaryResponse | null; loading: boolean; error: string | null }) {
  return (
    <div className="card" aria-live="polite">
      <div className="eyebrow">Today, in a sentence</div>
      <h2>Good {new Date().getHours() < 12 ? "morning" : "afternoon"}.</h2>
      {loading && <p className="empty">Reading today's activity…</p>}
      {error && <p className="error">{error}</p>}
      {summary?.text && <p style={{ fontSize: 17, margin: 0 }}>{summary.text}</p>}
    </div>
  );
}
