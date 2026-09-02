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

  it("strips inline Markdown from the aside: it is set in the serif, never bold or a heading", () => {
    expect(splitAside("**A quiet day.**\n\nBody.").aside).toBe("A quiet day.");
    expect(splitAside("_Quiet so far._\n\nBody.").aside).toBe("Quiet so far.");
    expect(splitAside("## Steady Tuesday.\n\nBody.").aside).toBe("Steady Tuesday.");
    expect(splitAside('"A strong Wednesday."\n\nBody.').aside).toBe("A strong Wednesday.");
    expect(splitAside("**A quiet day.**\n\nBody.").body).toBe("Body.");
  });

  it("counts the aside's words after stripping, so markers never disqualify a short line", () => {
    expect(splitAside("**Quiet so far.**\n\nBody.").aside).toBe("Quiet so far.");
  });

  it("treats a single paragraph as body only", () => {
    expect(splitAside("Nothing taken yet today.")).toEqual({
      aside: null,
      body: "Nothing taken yet today.",
    });
  });
});
