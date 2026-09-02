import { useCallback, useEffect, useState } from "react";

// Light or dark, via data-theme on <html>. The system preference is the
// default; only an explicit toggle is remembered, so a browser that later
// switches schemes is followed until the owner picks one. index.html applies
// the same rule before first paint so a reload never flashes the other theme.
export type Theme = "light" | "dark";

const KEY = "ledger.theme";

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch { /* storage unavailable */ }
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, next); } catch { /* storage unavailable */ }
      return next;
    });
  }, []);
  return [theme, toggle];
}
