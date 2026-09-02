// Every dollar amount on the page goes through Figure: cents in, mono out.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Figure } from "./Figure";

describe("Figure", () => {
  it("dims the cents on the hero figure", () => {
    const { container } = render(<Figure cents={241200} size="xl" tone="in" splitCents />);
    expect(container.textContent).toBe("$2,412.00");
    expect(container.querySelector(".cents")?.textContent).toBe(".00");
  });

  it("prefixes money out with a minus sign and keeps the cents inline", () => {
    const { container } = render(<Figure cents={4500} size="lg" tone="out" />);
    expect(container.textContent).toBe("−$45.00");
    expect(container.querySelector(".cents")).toBeNull();
  });
});
