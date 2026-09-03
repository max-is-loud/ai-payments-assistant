// React's development StrictMode mounts effects twice. The narration is one
// model call, so the second mount must reuse the first mount's request rather
// than ask again; and a refresh that fails must say so without discarding the
// numbers already on the page or pretending they are fresher than they are.
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

  it("asks the narrator once even though StrictMode mounts the effect twice", async () => {
    const narrations: Array<(value: unknown) => void> = [];
    vi.mocked(apiFetch).mockImplementation((path: string) => {
      if (path === "/api/summary/today") return new Promise((resolve) => narrations.push(resolve));
      if (path.startsWith("/api/summary/today?")) return Promise.resolve({ facts, text: null, currency: "usd" });
      if (path === "/api/summary/series") return Promise.resolve({ daily: [], hourly_today: [], top_customers: [] });
      if (path === "/api/escalations") return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected ${path}`));
    });

    render(<StrictMode><Harness /></StrictMode>);
    await waitFor(() => expect(narrations).toHaveLength(1));
    await act(async () => narrations[0]({ facts, text: "Once.", currency: "usd" }));
    expect(seen.latest?.summary?.text).toBe("Once.");
    // Nothing else asked for a narration in the meantime: one model call per page load.
    expect(vi.mocked(apiFetch).mock.calls.filter(([path]) => path === "/api/summary/today")).toHaveLength(1);
  });

  it("keeps the last good numbers and their time when a refresh fails, and can retry", async () => {
    let failing = false;
    vi.mocked(apiFetch).mockImplementation((path: string) => {
      if (failing) return Promise.reject(new Error("Couldn't reach the assistant API. Is it running?"));
      if (path === "/api/summary/today") return Promise.resolve({ facts, text: "Fine.", currency: "usd" });
      if (path.startsWith("/api/summary/today?")) return Promise.resolve({ facts, text: null, currency: "usd" });
      if (path === "/api/summary/series") return Promise.resolve({ daily: [], hourly_today: [], top_customers: [] });
      if (path === "/api/escalations") return Promise.resolve([]);
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    render(<Harness />);
    await waitFor(() => expect(seen.latest?.syncedAt).not.toBeNull());
    const synced = seen.latest!.syncedAt;
    expect(seen.latest?.refreshError).toBeNull();

    failing = true;
    await act(async () => seen.latest!.retryRefresh());
    await waitFor(() => expect(seen.latest?.refreshError).toContain("Couldn't reach the assistant API"));
    expect(seen.latest?.facts).toEqual(facts);
    expect(seen.latest?.syncedAt).toEqual(synced);

    failing = false;
    await act(async () => seen.latest!.retryRefresh());
    await waitFor(() => expect(seen.latest?.refreshError).toBeNull());
    expect(seen.latest!.syncedAt!.getTime()).toBeGreaterThanOrEqual(synced!.getTime());
  });
});
