// The narrator is asked to open with a one-line aside ("A strong Wednesday.").
// The hero renders it in the serif only when the model actually did that.
import { describe, expect, it } from "vitest";
import { splitAside } from "./summary";

describe("splitAside", () => {
  it("lifts a short first line off the summary", () => {
    const text = "A strong Wednesday.\n\nYou took **$2,412.00** across 18 payments today.";
    expect(splitAside(text)).toEqual({
      aside: "A strong Wednesday.",
      body: "You took **$2,412.00** across 18 payments today.",
    });
  });

  it("leaves a long first line alone: that is the summary itself, not an aside", () => {
    const text = "You took $2,412.00 across 18 payments today, well ahead of yesterday.\n\nTwo declined.";
    expect(splitAside(text)).toEqual({ aside: null, body: text });
  });

  it("treats a single paragraph as body only", () => {
    expect(splitAside("Nothing taken yet today.")).toEqual({
      aside: null,
      body: "Nothing taken yet today.",
    });
  });
});
