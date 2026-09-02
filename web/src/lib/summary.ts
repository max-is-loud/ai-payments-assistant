// The narrator is asked to open the daily summary with a one-line aside of a
// few words ("A strong Wednesday."). Only a first line that short is lifted
// into the serif greeting; anything longer is the summary itself, untouched.
const ASIDE_MAX_WORDS = 5;

export function splitAside(text: string): { aside: string | null; body: string } {
  const trimmed = text.trim();
  const newline = trimmed.indexOf("\n");
  if (newline === -1) return { aside: null, body: trimmed };
  const first = trimmed.slice(0, newline).trim();
  const words = first.split(/\s+/).filter(Boolean).length;
  if (words === 0 || words > ASIDE_MAX_WORDS) return { aside: null, body: trimmed };
  return { aside: first, body: trimmed.slice(newline).trim() };
}
