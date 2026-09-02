// An answer that compares two periods gets a chart drawn from the two
// query_payments observations already in the turn — no second request, and
// it works for whatever ranges the planner chose.
import type { AgentEvent, DayTotals } from "../api/types";

export interface ComparedPeriod {
  start: string;
  end: string;
  totalCents: number;
  count: number;
  daily: number[];
}

export interface Comparison {
  earlier: ComparedPeriod;
  later: ComparedPeriod;
}

interface RangedQuery {
  succeeded_total_cents: number;
  succeeded_count: number;
  daily_totals: DayTotals[];
}

// Only a successful query_payments with a date range carries daily_totals.
function rangedQuery(event: AgentEvent): RangedQuery | null {
  if (event.type !== "observation" || event.data.name !== "query_payments") return null;
  const result = event.data.result;
  if (typeof result !== "object" || result === null || "error" in result) return null;
  const query = result as Partial<RangedQuery>;
  if (!Array.isArray(query.daily_totals) || query.daily_totals.length === 0) return null;
  return query as RangedQuery;
}

function period(query: RangedQuery): ComparedPeriod {
  const days = query.daily_totals;
  return {
    start: days[0].date,
    end: days[days.length - 1].date,
    totalCents: query.succeeded_total_cents,
    count: query.succeeded_count,
    daily: days.map((d) => d.succeeded_total_cents),
  };
}

// The earlier period is the baseline whatever order the planner ran them in.
export function findComparison(events: AgentEvent[]): Comparison | null {
  const queries = events.map(rangedQuery).filter((q): q is RangedQuery => q !== null);
  if (queries.length < 2) return null;
  const [earlier, later] = queries
    .slice(0, 2)
    .map(period)
    .sort((a, b) => a.start.localeCompare(b.start));
  return { earlier, later };
}
