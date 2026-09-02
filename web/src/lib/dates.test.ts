// Dates in the owner app are human ("Aug 24 – 30"); ISO strings from the API
// are parsed as calendar dates, never shifted by the browser's timezone.
import { describe, expect, it } from "vitest";
import { dateRangeLabel, relativeAgo, shortDate, weekdayInitial } from "./dates";

describe("relativeAgo", () => {
  it("counts seconds, then minutes, then hours", () => {
    const now = new Date("2026-09-02T12:00:00Z");
    expect(relativeAgo(new Date("2026-09-02T11:59:48Z"), now)).toBe("12s ago");
    expect(relativeAgo(new Date("2026-09-02T11:57:00Z"), now)).toBe("3m ago");
    expect(relativeAgo(new Date("2026-09-02T10:00:00Z"), now)).toBe("2h ago");
  });
});

describe("shortDate", () => {
  it("renders an ISO date as month and day", () => {
    expect(shortDate("2026-08-12")).toBe("Aug 12");
    expect(shortDate("2026-09-02")).toBe("Sep 2");
  });
});

describe("dateRangeLabel", () => {
  it("drops the repeated month inside one month and keeps both across months", () => {
    expect(dateRangeLabel("2026-08-17", "2026-08-23")).toBe("Aug 17 – 23");
    expect(dateRangeLabel("2026-08-29", "2026-09-04")).toBe("Aug 29 – Sep 4");
  });
});

describe("weekdayInitial", () => {
  it("gives the one-letter weekday for a bar axis", () => {
    expect(["2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"].map(weekdayInitial))
      .toEqual(["M", "T", "W", "T", "F", "S", "S"]);
  });
});
