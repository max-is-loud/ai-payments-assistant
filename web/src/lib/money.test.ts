// Money formatting is the one place cents become text in the browser; the
// figure component and the trend stats both lean on these shapes.
import { describe, expect, it } from "vitest";
import { formatDollars, formatUsd, splitUsd } from "./money";

describe("splitUsd", () => {
  it("separates grouped dollars from the two-digit cents so the hero can dim them", () => {
    expect(splitUsd(241200)).toEqual({ dollars: "$2,412", cents: ".00" });
    expect(splitUsd(4505)).toEqual({ dollars: "$45", cents: ".05" });
  });

  it("keeps the sign in front of the dollar sign, like formatUsd", () => {
    expect(splitUsd(-4500)).toEqual({ dollars: "-$45", cents: ".00" });
    expect(formatUsd(-4500)).toBe("-$45.00");
  });
});

describe("formatDollars", () => {
  it("rounds to whole dollars for averages, which are not exact figures", () => {
    expect(formatDollars(88620)).toBe("$886");
    expect(formatDollars(88650)).toBe("$887");
    expect(formatDollars(123456700)).toBe("$1,234,567");
  });
});
