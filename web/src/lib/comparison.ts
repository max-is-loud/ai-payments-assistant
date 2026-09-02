// An answer that compares two periods gets a chart drawn from observations
// already in the turn — no second request. Either one compare_periods
// observation or two ranged query_payments observations will do.
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

// Per-day bars travel under `display`, the part of a result the server shows
// the interface but withholds from the model.
interface RangedQuery {
  succeeded_total_cents: number;
  succeeded_count: number;
  display: { daily_totals: DayTotals[] };
}

interface PeriodReport {
  start_date: string;
  end_date: string;
  succeeded_total_cents: number;
  succeeded_count: number;
}

interface ComparedQuery {
  earlier: PeriodReport;
  later: PeriodReport;
  display: { earlier_daily_totals: DayTotals[]; later_daily_totals: DayTotals[] };
}

function successfulResult(event: AgentEvent, action: string): Record<string, unknown> | null {
  if (event.type !== "observation" || event.data.name !== action) return null;
  const result = event.data.result;
  if (typeof result !== "object" || result === null || "error" in result) return null;
  return result as Record<string, unknown>;
}

function period(report: PeriodReport, days: DayTotals[]): ComparedPeriod {
  return {
    start: report.start_date,
    end: report.end_date,
    totalCents: report.succeeded_total_cents,
    count: report.succeeded_count,
    daily: days.map((d) => d.succeeded_total_cents),
  };
}

// compare_periods already names the earlier and later period.
function fromComparePeriods(event: AgentEvent): Comparison | null {
  const result = successfulResult(event, "compare_periods") as Partial<ComparedQuery> | null;
  if (!result?.earlier || !result.later || !result.display) return null;
  return {
    earlier: period(result.earlier, result.display.earlier_daily_totals ?? []),
    later: period(result.later, result.display.later_daily_totals ?? []),
  };
}

// Only a successful query_payments with a date range carries daily totals.
function rangedQuery(event: AgentEvent): RangedQuery | null {
  const result = successfulResult(event, "query_payments") as Partial<RangedQuery> | null;
  const days = result?.display?.daily_totals;
  if (!Array.isArray(days) || days.length === 0) return null;
  return result as RangedQuery;
}

function fromRangedQuery(query: RangedQuery): ComparedPeriod {
  const days = query.display.daily_totals;
  return period(
    {
      start_date: days[0].date,
      end_date: days[days.length - 1].date,
      succeeded_total_cents: query.succeeded_total_cents,
      succeeded_count: query.succeeded_count,
    },
    days,
  );
}

// With two ranged queries, the earlier period is the baseline whatever order
// the planner ran them in.
export function findComparison(events: AgentEvent[]): Comparison | null {
  for (const event of events) {
    const compared = fromComparePeriods(event);
    if (compared) return compared;
  }
  const queries = events.map(rangedQuery).filter((q): q is RangedQuery => q !== null);
  if (queries.length < 2) return null;
  const [earlier, later] = queries
    .slice(0, 2)
    .map(fromRangedQuery)
    .sort((a, b) => a.start.localeCompare(b.start));
  return { earlier, later };
}
