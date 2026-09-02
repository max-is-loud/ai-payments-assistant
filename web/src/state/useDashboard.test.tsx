// React's development StrictMode mounts effects twice, so the narration was
// requested twice and the model answered with two different texts: the first
// began typing, then the second replaced it and the effect restarted. A
// response belonging to a cleaned-up effect must be ignored.
//
// Rendered directly inside <StrictMode>: renderHook's wrapper does not trigger
// the double mount in this environment, a plain render does.
import { act, render, waitFor } from "@testing-library/react";
import { StrictMode, useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DailyFacts } from "../api/types";
import { apiFetch } from "../api/client";
import { useDashboard } from "./useDashboard";

vi.mock("../api/client", () => ({
  apiFetch: vi.fn(),
  describeError: (error: unknown) => String(error),
}));

const facts = {
  today: { label: "2026-09-02", succeeded_count: 1, succeeded_total_cents: 100, refunded_total_cents: 0, declined_count: 0, declined_reasons: {} },
  yesterday: { label: "2026-09-01", succeeded_count: 0, succeeded_total_cents: 0, refunded_total_cents: 0, declined_count: 0, declined_reasons: {} },
  open_invoices: [], open_invoice_total_cents: 0, largest_payment: null,
} as DailyFacts;

// Stable, as useConversation's useCallback is; a new function per render would re-run the effect.
const onMutation = () => () => undefined;

// The latest hook result, captured after each commit rather than during render.
const seen: { latest: ReturnType<typeof useDashboard> | null } = { latest: null };

function Harness() {
  const value = useDashboard(onMutation);
  useEffect(() => {
    seen.latest = value;
  });
  return null;
}

describe("useDashboard", () => {
  afterEach(() => {
    vi.mocked(apiFetch).mockReset();
    seen.latest = null;
    try {
      window.localStorage.clear();
    } catch {
      /* no storage in this environment */
    }
  });

  it("ignores a narration that answers after its effect was cleaned up", async () => {
    const narrations: Array<(value: unknown) => void> = [];
    vi.mocked(apiFetch).mockImplementation((path: string) => {
      if (path === "/api/summary/today") return new Promise((resolve) => narrations.push(resolve));
      if (path.startsWith("/api/summary/today?")) return Promise.resolve({ facts, text: null });
      if (path === "/api/summary/series") return Promise.resolve({ daily: [], hourly_today: [], top_customers: [] });
      if (path === "/api/escalations") return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected ${path}`));
    });

    render(<StrictMode><Harness /></StrictMode>);
    await waitFor(() => expect(narrations).toHaveLength(2));

    // The surviving mount's request answers first…
    await act(async () => narrations[1]({ facts, text: "Second." }));
    expect(seen.latest?.summary?.text).toBe("Second.");

    // …and the cleaned-up mount's late answer must not replace it.
    await act(async () => narrations[0]({ facts, text: "First." }));
    expect(seen.latest?.summary?.text).toBe("Second.");
  });
});
