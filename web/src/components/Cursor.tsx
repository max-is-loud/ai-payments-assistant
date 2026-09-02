// The blinking cursor that stands where model text is still being written, and
// rides the last character while it types in. It takes the colour of the text
// around it; reduced motion stops the blink in the stylesheet.
export function Cursor() {
  return <span className="ldg-cursor" aria-hidden="true" />;
}
