// Dates in the owner app are human: "Aug 24 – 30", "Wednesday, September 2".
// ISO dates from the API are calendar dates, so they are parsed at UTC noon and
// formatted in UTC — "2026-08-12" stays Aug 12 in every browser timezone.
const MONTH = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
const WEEKDAY = new Intl.DateTimeFormat("en-US", { weekday: "narrow", timeZone: "UTC" });
const CLOCK = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
const DAY_MS = 86_400_000;

function parse(iso: string): Date {
  return new Date(`${iso}T12:00:00Z`);
}

export function shortDate(iso: string): string {
  return `${MONTH.format(parse(iso))} ${parse(iso).getUTCDate()}`;
}

export function dateRangeLabel(start: string, end: string): string {
  if (start === end) return shortDate(start);
  const sameMonth = start.slice(0, 7) === end.slice(0, 7);
  return sameMonth
    ? `${shortDate(start)} – ${parse(end).getUTCDate()}`
    : `${shortDate(start)} – ${shortDate(end)}`;
}

export function weekdayInitial(iso: string): string {
  return WEEKDAY.format(parse(iso));
}

export function isWeekday(iso: string): boolean {
  const day = parse(iso).getUTCDay();
  return day >= 1 && day <= 5;
}

export function addDays(iso: string, days: number): string {
  return new Date(parse(iso).getTime() + days * DAY_MS).toISOString().slice(0, 10);
}

export function longDate(now: Date = new Date()): string {
  return now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

// "12s ago", "3m ago" — the masthead's sync stamp.
export function relativeAgo(then: Date, now: Date): string {
  const seconds = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.round(seconds / 60)}m ago`;
}

// The database stores naive UTC timestamps; the suffix tells the browser so.
export function utcClock(naiveIso: string): string {
  return CLOCK.format(new Date(`${naiveIso}Z`));
}
