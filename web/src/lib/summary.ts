// The narrator is asked to open the daily summary with a one-line aside of a
// few words ("A strong Wednesday."). Only a first line that short is lifted
// into the serif greeting; anything longer is the summary itself, untouched.
const ASIDE_MAX_WORDS = 5;

// The aside is set in the serif at one weight and size, so any Markdown the
// model wraps it in — bold, italics, a heading, quotation marks from copying
// the prompt's example — is stripped rather than rendered or shown literally.
export function stripInlineMarkdown(line: string): string {
  return line
    .replace(/^#{1,6}\s+/, "")
    .replace(/[*_`]+/g, "")
    .replace(/^["“”']+|["“”']+$/g, "")
    .trim();
}

export function splitAside(text: string): { aside: string | null; body: string } {
  const trimmed = text.trim();
  const newline = trimmed.indexOf("\n");
  if (newline === -1) return { aside: null, body: trimmed };
  const first = stripInlineMarkdown(trimmed.slice(0, newline));
  const words = first.split(/\s+/).filter(Boolean).length;
  if (words === 0 || words > ASIDE_MAX_WORDS) return { aside: null, body: trimmed };
  return { aside: first, body: trimmed.slice(newline).trim() };
}
