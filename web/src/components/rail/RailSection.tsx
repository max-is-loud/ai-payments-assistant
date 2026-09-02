import type { ReactNode } from "react";
import { Eyebrow } from "../Eyebrow";

// Borderless rail block: an underlined eyebrow, the content, an optional
// one-sentence note. The escalation card is the only bordered thing in the rail.
export function RailSection({ title, note, children }: {
  title: ReactNode;
  note?: string;
  children: ReactNode;
}) {
  return (
    <section className="ldg-rail-section">
      <Eyebrow>{title}</Eyebrow>
      {children}
      {note && <div className="note">{note}</div>}
    </section>
  );
}
