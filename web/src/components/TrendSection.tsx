import type { DayTotals } from "../api/types";
import { shortDate } from "../lib/dates";
import { formatMoney, formatWhole } from "../lib/money";
import { trendStats } from "../lib/series";
import { useCurrency } from "../state/useCurrency";
import { AreaChart } from "./charts/AreaChart";
import { Axis } from "./charts/Bars";
import { Eyebrow } from "./Eyebrow";

// The axis names the first day, two evenly spaced days, and today.
function axisLabels(days: DayTotals[]): string[] {
  if (days.length < 2) return [];
  const at = (fraction: number) => shortDate(days[Math.round((days.length - 1) * fraction)].date);
  return [at(0), at(1 / 3), at(2 / 3), "Today"];
}

// Three weeks of takings as an area, with the stats row the chart implies.
// `daily` is null until the series arrives; the chart then draws its gridlines only.
export function TrendSection({ daily }: { daily: DayTotals[] | null }) {
  const currency = useCurrency();
  const days = daily ?? [];
  const values = days.map((d) => d.succeeded_total_cents);
  const stats = trendStats(days);
  const first = days[0]?.date;
  const last = days[days.length - 1]?.date;
  const bestIsToday = stats.bestDay !== null && stats.bestDay === last;
  return (
    <section className="ldg-trend" aria-label="Taken per day">
      <div className="head">
        <Eyebrow>Taken per day{first ? ` · ${shortDate(first)} – today` : ""}</Eyebrow>
        {daily && (
          <div className="ldg-stats">
            <span>3-week total <strong>{formatMoney(stats.totalCents, currency)}</strong></span>
            <span>Weekday avg <strong>{formatWhole(stats.weekdayAvgCents, currency)}</strong></span>
            <span>
              Best day{" "}
              <strong className={bestIsToday ? "in" : ""}>
                {stats.bestDay ? (bestIsToday ? "Today" : shortDate(stats.bestDay)) : "—"}
              </strong>
            </span>
          </div>
        )}
      </div>
      <AreaChart values={values} maxLabel={stats.totalCents ? formatMoney(Math.max(...values), currency) : undefined}>
        {daily === null && <p className="ldg-empty">Loading three weeks of takings…</p>}
      </AreaChart>
      <Axis labels={axisLabels(days)} lastTone="in" />
    </section>
  );
}
