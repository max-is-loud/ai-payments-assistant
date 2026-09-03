// Money formatting is the one place cents become text in the browser; the
// figure component and the trend stats both lean on these shapes, and the
// symbol has to follow the account rather than assume dollars.
import { describe, expect, it } from "vitest";
import { formatMoney, formatWhole, splitMoney } from "./money";

describe("formatMoney", () => {
  it("groups thousands and keeps two decimals, sign first", () => {
    expect(formatMoney(120000, "usd")).toBe("$1,200.00");
    expect(formatMoney(-4500, "usd")).toBe("-$45.00");
    expect(formatMoney(0, "usd")).toBe("$0.00");
  });

  it("carries the account's symbol, matching the Python side's table", () => {
    expect(formatMoney(120000, "cad")).toBe("CA$1,200.00");
    expect(formatMoney(120000, "eur")).toBe("€1,200.00");
    expect(formatMoney(120000, "gbp")).toBe("£1,200.00");
  });
});

describe("splitMoney", () => {
  it("separates grouped units from the two-digit cents so the hero can dim them", () => {
    expect(splitMoney(241200, "usd")).toEqual({ units: "$2,412", cents: ".00" });
    expect(splitMoney(4505, "usd")).toEqual({ units: "$45", cents: ".05" });
  });

  it("keeps the sign and the symbol with the units, whatever the symbol is", () => {
    expect(splitMoney(-4500, "usd")).toEqual({ units: "-$45", cents: ".00" });
    expect(splitMoney(241200, "cad")).toEqual({ units: "CA$2,412", cents: ".00" });
  });
});

describe("formatWhole", () => {
  it("rounds to whole units for averages, which are not exact figures", () => {
    expect(formatWhole(88620, "usd")).toBe("$886");
    expect(formatWhole(88650, "usd")).toBe("$887");
    expect(formatWhole(123456700, "usd")).toBe("$1,234,567");
    expect(formatWhole(88620, "cad")).toBe("CA$886");
  });
});
