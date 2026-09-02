// Reveal the first `count` characters of a Markdown source without ever
// showing a half-open span: a bold or code span cut mid-way is closed at the
// cut, and an opener with nothing after it yet is held back. Only the two
// constructs the narrator is asked for — **bold** figures and `code` ids —
// are handled; anything else renders as it would in full.
export function revealMarkdown(source: string, count: number): string {
  if (count >= source.length) return source;
  let visible = source.slice(0, Math.max(0, count));
  // Half of a `**` opener: wait for its other half.
  if (visible.endsWith("*") && source[visible.length] === "*") visible = visible.slice(0, -1);
  // An opener with nothing after it would render as literal asterisks.
  if (visible.endsWith("**") && occurrences(visible, "**") % 2 === 1) visible = visible.slice(0, -2);
  if (occurrences(visible, "**") % 2 === 1) visible += "**";
  if (occurrences(visible, "`") % 2 === 1) {
    visible = visible.endsWith("`") ? visible.slice(0, -1) : `${visible}\``;
  }
  return visible;
}

function occurrences(text: string, needle: string): number {
  return text.split(needle).length - 1;
}
