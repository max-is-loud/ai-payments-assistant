import { useEffect, useState } from "react";

// The current time, re-read every `everyMs`, so "synced 12s ago" keeps counting.
export function useTicker(everyMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(timer);
  }, [everyMs]);
  return now;
}
