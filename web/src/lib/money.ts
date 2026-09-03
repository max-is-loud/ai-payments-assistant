// The browser-side twin of app/domain/money.py. Cents in, a figure in the
// account's currency out, nothing else. `Intl` supplies the symbol the way the
// Python side's table does — CA$ for CAD, $ for USD, € for EUR — so a figure
// reads the same on the page as in a narrated sentence.

// Lowercase ISO 4217, as Stripe reports it and as /api/summary/today relays it.
export type CurrencyCode = string;

function formatter(currency: CurrencyCode, digits: 0 | 2): Intl.NumberFormat {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatMoney(cents: number, currency: CurrencyCode): string {
  return formatter(currency, 2).format(cents / 100);
}

// The hero figure dims its cents; every other figure prints them inline. The
// split falls at the decimal separator, so the sign and symbol stay with the
// units whatever the currency puts in front of the number.
export function splitMoney(cents: number, currency: CurrencyCode): { units: string; cents: string } {
  const parts = formatter(currency, 2).formatToParts(cents / 100);
  const at = parts.findIndex((p) => p.type === "decimal");
  const join = (slice: Intl.NumberFormatPart[]) => slice.map((p) => p.value).join("");
  return { units: join(parts.slice(0, at)), cents: join(parts.slice(at)) };
}

// Averages are not exact figures, so the design prints them as whole units.
export function formatWhole(cents: number, currency: CurrencyCode): string {
  return formatter(currency, 0).format(Math.round(cents / 100));
}
