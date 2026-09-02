// A cold chart says it is loading; bare gridlines read as broken.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrendSection } from "./TrendSection";

describe("TrendSection", () => {
  it("says it is loading until the series arrives", () => {
    const { container } = render(<TrendSection daily={null} />);
    expect(container.querySelector(".ldg-area .ldg-empty")?.textContent).toBe("Loading three weeks of takings…");
    expect(container.querySelector(".ldg-stats")).toBeNull();
  });

  it("draws the series and its stats once it has them", () => {
    const daily = [
      { date: "2026-08-31", succeeded_total_cents: 100_00, succeeded_count: 1 },
      { date: "2026-09-01", succeeded_total_cents: 300_00, succeeded_count: 2 },
    ];
    const { container } = render(<TrendSection daily={daily} />);
    expect(container.querySelector(".ldg-area .ldg-empty")).toBeNull();
    expect(container.querySelector(".ldg-stats")?.textContent).toContain("3-week total $400.00");
    expect(container.querySelector(".ldg-area path.line")).not.toBeNull();
  });
});
