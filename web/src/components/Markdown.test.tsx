// The web formatting boundary: model text renders as GFM, and nothing else.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("renders a bulleted list one item per line", () => {
    const text =
      "Today:\n- Acme Corp — $24.00 — succeeded\n- Maya Chen — $44.00 — refunded\n- Doyle Ltd — $34.00 — failed";
    const { container } = render(<Markdown>{text}</Markdown>);
    expect(container.querySelectorAll("ul > li")).toHaveLength(3);
  });

  it("renders a GFM table", () => {
    const text = "| Customer | Amount |\n| --- | --- |\n| Acme Corp | $24.00 |";
    const { container } = render(<Markdown>{text}</Markdown>);
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelectorAll("td")).toHaveLength(2);
  });

  it("keeps plain prose as a paragraph with emphasis", () => {
    const { container } = render(<Markdown>{"You took **$2,809.00** today."}</Markdown>);
    expect(container.querySelector("p strong")?.textContent).toBe("$2,809.00");
  });

  it("never renders raw HTML as elements", () => {
    const text = "Paid <b>F-0001</b> <script>alert(1)</script>";
    const { container } = render(<Markdown>{text}</Markdown>);
    expect(container.querySelector("b, script")).toBeNull();
    expect(container.textContent).toContain("F-0001");
  });

  it("neutralises javascript: links", () => {
    const { container } = render(<Markdown>{"[receipt](javascript:alert(1))"}</Markdown>);
    expect(container.querySelector("a")?.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
  });
});
