import { createContext, useContext } from "react";
import type { CurrencyCode } from "../lib/money";

// The account settles in one currency. It arrives on /api/summary/today and
// is held here so every figure formats in it without a prop threaded through
// the charts. Dollars until the first response lands — and in tests that
// render a component on its own.
const CurrencyContext = createContext<CurrencyCode>("usd");

export const CurrencyProvider = CurrencyContext.Provider;

export function useCurrency(): CurrencyCode {
  return useContext(CurrencyContext);
}
