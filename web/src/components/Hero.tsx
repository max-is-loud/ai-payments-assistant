import type { DailyFacts, SummaryResponse } from "../api/types";
import { revealMarkdown } from "../lib/reveal";
import { splitAside } from "../lib/summary";
import { useTypewriter } from "../state/useTypewriter";
import { Cursor } from "./Cursor";
import { ErrorStrip } from "./ErrorStrip";
import { Eyebrow } from "./Eyebrow";
import { Figure } from "./Figure";
import { Markdown } from "./Markdown";
import { Pill } from "./Pill";

// The narrated text arrives whole; it is revealed as if streamed — the aside
// first, then the lede — purely for the feel of an assistant that is speaking.
const ASIDE_MS = 500;
const LEDE_MS = 1500;

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

// The app speaks first. Left: a cursor holds the aside's place while the
// narrator works, then the aside and the lede type in. Right: today's figure
// and pills, computed from facts, never prose.
export function Hero({ summary, loading, error, facts, now = new Date() }: {
  summary: SummaryResponse | null;
  loading: boolean;
  error: string | null;
  facts: DailyFacts | null;
  now?: Date;
}) {
  const split = summary?.text ? splitAside(summary.text) : null;
  const aside = useTypewriter(split ? split.aside ?? "" : null, true, ASIDE_MS);
  const lede = useTypewriter(split ? split.body : null, aside.done, LEDE_MS);
  const delta = facts ? change(facts.today.succeeded_total_cents, facts.yesterday.succeeded_total_cents) : null;
  return (
    <section className="ldg-hero">
      <div>
        <Eyebrow>Today, in a sentence</Eyebrow>
        <h1 className="ldg-hero-title">
          {greeting(now)}{" "}
          {loading && <em><Cursor /></em>}
          {split?.aside && (
            <em>
              {split.aside.slice(0, aside.shown)}
              {!aside.done && <Cursor />}
            </em>
          )}
        </h1>
        {error && <ErrorStrip>{error}</ErrorStrip>}
        {split && aside.done && (
          <div className={lede.done ? "ldg-lede" : "ldg-lede typing"}>
            <Markdown>{revealMarkdown(split.body, lede.shown)}</Markdown>
            {!lede.done && <Cursor />}
          </div>
        )}
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
