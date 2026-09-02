// A Markdown source revealed a few characters at a time must never flash a
// stray `**` or backtick: an open span is closed at the cut so the partial
// text renders bold or as code the whole way through.
import { describe, expect, it } from "vitest";
import { revealMarkdown } from "./reveal";

const source = "You took **$2,578.00** across 18 payments and `pi_1` failed.";

describe("revealMarkdown", () => {
  it("returns the whole source once everything is revealed", () => {
    expect(revealMarkdown(source, source.length)).toBe(source);
    expect(revealMarkdown(source, source.length + 50)).toBe(source);
  });

  it("closes a bold span cut in the middle", () => {
    expect(revealMarkdown(source, 13)).toBe("You took **$2**");
  });

  it("drops an opener that has nothing after it yet, instead of rendering four asterisks", () => {
    expect(revealMarkdown(source, 11)).toBe("You took ");
    expect(revealMarkdown(source, 10)).toBe("You took ");
  });

  it("closes a code span cut in the middle", () => {
    expect(revealMarkdown(source, 49)).toBe("You took **$2,578.00** across 18 payments and `pi`");
  });

  it("reveals nothing for zero", () => {
    expect(revealMarkdown(source, 0)).toBe("");
  });
});
