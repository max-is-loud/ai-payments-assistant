// The thread wires the turn state to the cards: a comparison chart appears
// when a turn compared two ranges, and a failed send can be retried verbatim.
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AgentEvent } from "../api/types";
import type { Turn } from "../state/useConversation";
import { Thread } from "./Thread";

const ranged = (start: string, cents: number): AgentEvent => ({
  type: "observation",
  data: { name: "query_payments", result: {
    period: `${start} to ${start}`, succeeded_total_cents: cents, succeeded_count: 1,
    display: { daily_totals: [{ date: start, succeeded_total_cents: cents, succeeded_count: 1 }] },
  } },
});

const noop = () => undefined;

describe("Thread", () => {
  it("draws the comparison chart inside the answer when the turn compared two ranges", () => {
    const turns: Turn[] = [
      { id: "u1", role: "user", text: "Compare the weeks", events: [] },
      { id: "a1", role: "assistant", text: "Up **14.6%**.", events: [ranged("2026-08-24", 528400), ranged("2026-08-17", 461000)] },
    ];
    const { container } = render(<Thread turns={turns} busy={false} error={null} onApprove={noop} onCancel={noop} onRetry={noop} />);
    const bubble = container.querySelector(".ldg-bubble");
    expect(bubble?.querySelector(".ldg-compare")).not.toBeNull();
    expect(bubble?.querySelector("strong")?.textContent).toBe("14.6%");
  });

  it("does not draw a chart for an ordinary answer", () => {
    const turns: Turn[] = [
      { id: "u1", role: "user", text: "Who is Maya?", events: [] },
      { id: "a1", role: "assistant", text: "Maya Chen.", events: [{ type: "observation", data: { name: "find_customer", result: { count: 1 } } }] },
    ];
    const { container } = render(<Thread turns={turns} busy={false} error={null} onApprove={noop} onCancel={noop} onRetry={noop} />);
    expect(container.querySelector(".ldg-compare")).toBeNull();
  });

  it("retries a failed send with the same words", () => {
    const onRetry = vi.fn();
    const turns: Turn[] = [
      { id: "u1", role: "user", text: "Refund Maya's last payment.", events: [] },
      { id: "a1", role: "assistant", events: [], error: "Couldn't reach the assistant API. Is it running?" },
    ];
    const { getByRole } = render(<Thread turns={turns} busy={false} error={null} onApprove={noop} onCancel={noop} onRetry={onRetry} />);
    fireEvent.click(getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledWith("Refund Maya's last payment.");
  });
});
