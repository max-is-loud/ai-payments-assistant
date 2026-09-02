import type { DailyFacts, SummaryResponse } from "../api/types";
import { splitAside } from "../lib/summary";
import { ErrorStrip } from "./ErrorStrip";
import { Eyebrow } from "./Eyebrow";
import { Figure } from "./Figure";
import { Markdown } from "./Markdown";
import { Pill } from "./Pill";

function greeting(now: Date): string {
  const hour = now.getHours();
  return hour < 12 ? "Good morning." : hour < 18 ? "Good afternoon." : "Good evening.";
}

// "+80.5% vs yesterday", one decimal; nothing when yesterday has nothing to compare against.
function change(today: number, yesterday: number): { label: string; tone: "in" | "out" | "neutral" } | null {
  if (yesterday <= 0) return null;
  const pct = ((today - yesterday) / yesterday) * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return {
    label: `${sign}${Math.abs(pct).toFixed(1)}% vs yesterday`,
    tone: pct > 0 ? "in" : pct < 0 ? "out" : "neutral",
  };
}

// The app speaks first. Left: the narrator's aside in the serif and the lede as
// Markdown. Right: today's figure and pills, all computed from facts, never prose.
export function Hero({ summary, loading, error, facts, now = new Date() }: {
  summary: SummaryResponse | null;
  loading: boolean;
  error: string | null;
  facts: DailyFacts | null;
  now?: Date;
}) {
  const split = summary?.text ? splitAside(summary.text) : null;
  const delta = facts ? change(facts.today.succeeded_total_cents, facts.yesterday.succeeded_total_cents) : null;
  return (
    <section className="ldg-hero" aria-live="polite">
      <div>
        <Eyebrow>Today, in a sentence</Eyebrow>
        <h1 className="ldg-hero-title">
          {greeting(now)} {split?.aside && <em>{split.aside}</em>}
        </h1>
        {loading && <p className="ldg-empty">Reading today's activity…</p>}
        {error && <ErrorStrip>{error}</ErrorStrip>}
        {split && <div className="ldg-lede"><Markdown>{split.body}</Markdown></div>}
      </div>
      <div className="right">
        <Eyebrow>Taken today</Eyebrow>
        {facts ? (
          <Figure cents={facts.today.succeeded_total_cents} size="xl" tone="in" splitCents />
        ) : (
          <span className="ldg-figure xl placeholder">—</span>
        )}
        {facts && (
          <div className="ldg-pills">
            {delta && <Pill tone={delta.tone}>{delta.label}</Pill>}
            <Pill>{facts.today.succeeded_count} {facts.today.succeeded_count === 1 ? "payment" : "payments"}</Pill>
            {facts.today.declined_count > 0 && <Pill tone="out">{facts.today.declined_count} declined</Pill>}
          </div>
        )}
      </div>
    </section>
  );
}
