import React from "react";
import { Eyebrow } from "./Eyebrow.jsx";
/** Borderless rail block: eyebrow with hairline underneath, then content, optional note sentence. */
export function RailSection({ title, note, children }) {
  return <section className="ldg-rail-section"><Eyebrow>{title}</Eyebrow>{children}{note && <div className="note">{note}</div>}</section>;
}