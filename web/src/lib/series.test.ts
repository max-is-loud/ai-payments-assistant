// The trend's stats row and the rail's hourly chart derive their words from
// the series; the model never sees these numbers.
import { describe, expect, it } from "vitest";
import type { DayTotals, HourTotals } from "../api/types";
import { hourlyView, trendStats } from "./series";

const day = (date: string, cents: number): DayTotals => ({
  date, succeeded_total_cents: cents, succeeded_count: cents ? 1 : 0,
});

// 2026-08-31 is a Monday; 2026-09-05 and 06 are the weekend.
const daily: DayTotals[] = [
  day("2026-08-31", 100_00), day("2026-09-01", 300_00), day("2026-09-05", 50_00),
  day("2026-09-06", 0), day("2026-09-07", 200_00),
];

const quietDay = (): HourTotals[] =>
  Array.from({ length: 24 }, (_, hour) => ({ hour, succeeded_total_cents: 0, succeeded_count: 0 }));

const withActivity = (...entries: [number, number, number][]): HourTotals[] => {
  const hours = quietDay();
  for (const [hour, cents, count] of entries) hours[hour] = { hour, succeeded_total_cents: cents, succeeded_count: count };
  return hours;
};

describe("trendStats", () => {
  it("totals every day, averages weekdays only, and names the best day", () => {
    expect(trendStats(daily)).toEqual({ totalCents: 650_00, weekdayAvgCents: 200_00, bestDay: "2026-09-01" });
  });

  it("has no best day when nothing was taken", () => {
    expect(trendStats([day("2026-08-31", 0), day("2026-09-01", 0)])).toEqual({
      totalCents: 0, weekdayAvgCents: 0, bestDay: null,
    });
  });
});

describe("hourlyView", () => {
  it("shows business hours with three axis labels and says when the day got busy", () => {
    const view = hourlyView(withActivity([9, 250_00, 1], [15, 486_00, 3]), "usd");
    expect(view.hours.map((h) => h.hour)).toEqual([8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]);
    expect(view.labels).toEqual(["8am", "1pm", "6pm"]);
    expect(view.note).toBe("Busiest at 3pm: $486.00 across 3 payments. Nothing before 9am.");
  });

  it("widens the axis when payments land outside business hours", () => {
    const late = hourlyView(withActivity([20, 12_00, 1]), "usd");
    expect(late.hours[late.hours.length - 1].hour).toBe(20);
    expect(late.labels).toEqual(["8am", "2pm", "8pm"]);
    const early = hourlyView(withActivity([6, 12_00, 1], [9, 5_00, 1]), "usd");
    expect(early.hours[0].hour).toBe(6);
    expect(early.note).toBe("Busiest at 6am: $12.00 across 1 payment.");
  });

  it("says so when nothing has been taken yet", () => {
    const view = hourlyView(quietDay(), "usd");
    expect(view.hours.map((h) => h.hour)).toEqual([8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]);
    expect(view.note).toBe("Nothing taken yet today.");
  });
});
