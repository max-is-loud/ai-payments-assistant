// The browser-side twin of app/domain/money.py. Cents in, dollars out, nothing else.
export function formatUsd(cents: number): string {
  const { dollars, cents: fraction } = splitUsd(cents);
  return dollars + fraction;
}

// The hero figure dims its cents; every other figure prints them inline.
export function splitUsd(cents: number): { dollars: string; cents: string } {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return {
    dollars: `${sign}$${Math.floor(abs / 100).toLocaleString("en-US")}`,
    cents: `.${String(abs % 100).padStart(2, "0")}`,
  };
}

// Averages are not exact figures, so the design prints them as whole dollars.
export function formatDollars(cents: number): string {
  const dollars = Math.round(cents / 100);
  return `${dollars < 0 ? "-" : ""}$${Math.abs(dollars).toLocaleString("en-US")}`;
}
