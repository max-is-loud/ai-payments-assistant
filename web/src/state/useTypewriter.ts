import { useEffect, useState } from "react";

// Paces the reveal of text that has already arrived whole, so it reads as if
// the assistant were speaking. `text` is null until it arrives; `active` lets
// one passage wait for another to finish. The whole reveal takes `durationMs`
// whatever the length, so a long lede never crawls. Readers who prefer reduced
// motion get everything at once.
const TICK_MS = 30;

interface Progress {
  passage: string | null;
  shown: number;
}

function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useTypewriter(
  text: string | null,
  active: boolean,
  durationMs: number,
): { shown: number; done: boolean } {
  const reduced = prefersReducedMotion();
  const passage = active && text !== null ? text : null;
  // Progress remembers which passage it belongs to, so a new passage reads as
  // zero until its own ticks arrive — no reset needed inside the effect.
  const [progress, setProgress] = useState<Progress>({ passage: null, shown: 0 });

  useEffect(() => {
    if (passage === null || reduced || passage.length === 0) return;
    const started = Date.now();
    const timer = setInterval(() => {
      const ratio = Math.min(1, (Date.now() - started) / durationMs);
      setProgress({ passage, shown: Math.ceil(ratio * passage.length) });
      if (ratio >= 1) clearInterval(timer);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [passage, durationMs, reduced]);

  let shown = 0;
  if (passage !== null) {
    if (reduced || passage.length === 0) shown = passage.length;
    else if (progress.passage === passage) shown = progress.shown;
  }
  return { shown, done: passage !== null && shown >= passage.length };
}
