// Words and ranges derived from the chart series. The model never sees these
// numbers; the trend's stats row and the rail's hourly note are computed here.
import type { DayTotals, HourTotals } from "../api/types";
import { isWeekday } from "./dates";
import { type CurrencyCode, formatMoney } from "./money";

const BUSINESS_START = 8;
const BUSINESS_END = 18;

export interface TrendStats {
  totalCents: number;
  weekdayAvgCents: number;
  bestDay: string | null;
}

export function trendStats(daily: DayTotals[]): TrendStats {
  const sum = (days: DayTotals[]) => days.reduce((acc, d) => acc + d.succeeded_total_cents, 0);
  const weekdays = daily.filter((d) => isWeekday(d.date));
  const best = daily.reduce<DayTotals | null>(
    (acc, d) => (d.succeeded_total_cents > (acc?.succeeded_total_cents ?? 0) ? d : acc),
    null,
  );
  return {
    totalCents: sum(daily),
    weekdayAvgCents: weekdays.length ? Math.round(sum(weekdays) / weekdays.length) : 0,
    bestDay: best?.date ?? null,
  };
}

// A day with nothing in it yet, for the chart's loading state.
export function emptyHourly(): HourTotals[] {
  return Array.from({ length: 24 }, (_, hour) => ({ hour, succeeded_total_cents: 0, succeeded_count: 0 }));
}

export function formatHour(hour: number): string {
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}${hour < 12 ? "am" : "pm"}`;
}

export interface HourlyView {
  hours: HourTotals[];
  labels: string[];
  note: string;
}

// Business hours by default, widened to include any hour that saw a payment:
// today's seeded payments land at whatever hour the reviewer ran the seed.
export function hourlyView(hourly: HourTotals[], currency: CurrencyCode): HourlyView {
  const active = hourly.filter((h) => h.succeeded_count > 0);
  const start = Math.min(BUSINESS_START, active[0]?.hour ?? BUSINESS_START);
  const end = Math.max(BUSINESS_END, active[active.length - 1]?.hour ?? BUSINESS_END);
  return {
    hours: hourly.filter((h) => h.hour >= start && h.hour <= end),
    labels: [start, Math.floor((start + end) / 2), end].map(formatHour),
    note: hourlyNote(active, start, currency),
  };
}

function hourlyNote(active: HourTotals[], start: number, currency: CurrencyCode): string {
  if (!active.length) return "Nothing taken yet today.";
  const busiest = active.reduce((a, b) => (b.succeeded_total_cents > a.succeeded_total_cents ? b : a));
  const payments = busiest.succeeded_count === 1 ? "payment" : "payments";
  const lead =
    `Busiest at ${formatHour(busiest.hour)}: ${formatMoney(busiest.succeeded_total_cents, currency)} ` +
    `across ${busiest.succeeded_count} ${payments}.`;
  const first = active[0].hour;
  return first > start ? `${lead} Nothing before ${formatHour(first)}.` : lead;
}
