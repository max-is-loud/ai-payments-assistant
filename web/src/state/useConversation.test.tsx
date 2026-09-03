// Approval is a claim about money, so the card may only say "Approved" once
// the server has streamed the executed result. Until then it says the
// approval is in flight; if the request fails, or the stream ends with an
// error frame instead of a result, the card goes back to its buttons with the
// failure under it, and the dashboard is not told anything moved.
import { act, render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentEvent } from "../api/types";
import { apiFetch, streamTurn } from "../api/client";
import { useConversation } from "./useConversation";

// Only the network is faked; ApiError and describeError are the real ones, so
// the sentences asserted below are the ones the owner would read.
vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  apiFetch: vi.fn(),
  streamTurn: vi.fn(),
}));

const seen: { latest: ReturnType<typeof useConversation> | null } = { latest: null };

function Harness() {
  const value = useConversation();
  useEffect(() => {
    seen.latest = value;
  });
  return null;
}

const confirmationEvent: AgentEvent = {
  type: "confirmation",
  data: { action_id: "act_1", action: "refund_payment", summary: "Refund $45.00 to Maya Chen", parameters: {} },
};

const executed: AgentEvent[] = [
  { type: "action", data: { name: "refund_payment", args: { payment_id: "pi_1" } } },
  { type: "observation", data: { name: "refund_payment", result: { amount_cents: 4500 } } },
  { type: "answer", data: { text: "Refunded $45.00.", result: { action: "refund_payment", data: { amount_cents: 4500 } } } },
];

type Emit = (event: AgentEvent) => void;

// Script the next stream: emit the given events, then resolve or reject.
function nextStream(events: AgentEvent[], outcome: "resolve" | "reject" = "resolve") {
  vi.mocked(streamTurn).mockImplementationOnce(async (_path: string, _body: unknown, onEvent: Emit) => {
    events.forEach(onEvent);
    if (outcome === "reject") throw new Error("The assistant API didn't answer (HTTP 502). Is it running?");
  });
}

const turnFor = (id: string) => seen.latest?.turns.find((t) => t.id === id);

async function proposeRefund() {
  vi.mocked(apiFetch).mockResolvedValue({ conversation_id: "c", messages: [], pending: null });
  render(<Harness />);
  await waitFor(() => expect(seen.latest).not.toBeNull());
  nextStream([confirmationEvent]);
  await act(async () => seen.latest!.send("refund maya"));
  await waitFor(() => expect(turnFor("act_1")?.confirmation).toBeTruthy());
  const moved = vi.fn();
  seen.latest!.onMutation(moved);
  return moved;
}

describe("useConversation approve", () => {
  afterEach(() => {
    vi.mocked(apiFetch).mockReset();
    vi.mocked(streamTurn).mockReset();
    seen.latest = null;
    try {
      window.localStorage.clear();
    } catch {
      /* no storage in this environment */
    }
  });

  it("says the approval is in flight, then approved only once the executed result has arrived", async () => {
    const moved = await proposeRefund();
    let finish: () => void = () => undefined;
    vi.mocked(streamTurn).mockImplementationOnce(
      (_path: string, _body: unknown, onEvent: Emit) =>
        new Promise<void>((resolve) => {
          finish = () => {
            executed.forEach(onEvent);
            resolve();
          };
        }),
    );
    let approval: Promise<void> = Promise.resolve();
    act(() => {
      approval = seen.latest!.approve("act_1");
    });
    await waitFor(() => expect(turnFor("act_1")?.decided).toBe("approving"));
    expect(moved).not.toHaveBeenCalled();
    await act(async () => {
      finish();
      await approval;
    });
    expect(turnFor("act_1")?.decided).toBe("approved");
    expect(seen.latest!.turns.at(-1)?.result).toEqual({ action: "refund_payment", data: { amount_cents: 4500 } });
    expect(moved).toHaveBeenCalledTimes(1);
    // The key is the server's; the client sends none.
    expect(vi.mocked(streamTurn).mock.calls[1][3]).toBeUndefined();
  });

  it("leaves the card unapproved and retryable when the request itself fails", async () => {
    const moved = await proposeRefund();
    nextStream([], "reject");
    await act(async () => seen.latest!.approve("act_1"));
    const turn = turnFor("act_1");
    expect(turn?.decided).toBeUndefined();
    expect(turn?.error).toBe("The assistant API didn't answer (HTTP 502). Is it running?");
    expect(seen.latest!.turns.at(-1)?.id).toBe("act_1");
    expect(moved).not.toHaveBeenCalled();
  });

  it("leaves the card unapproved when the stream ends with an error frame instead of a result", async () => {
    const moved = await proposeRefund();
    nextStream([{ type: "error", data: { code: "stripe_error", message: "Stripe couldn't complete that request.", hint: "Try again." } }]);
    await act(async () => seen.latest!.approve("act_1"));
    const turn = turnFor("act_1");
    expect(turn?.decided).toBeUndefined();
    expect(turn?.error).toBe("Stripe couldn't complete that request. Try again.");
    expect(seen.latest!.turns.at(-1)?.id).toBe("act_1");
    expect(moved).not.toHaveBeenCalled();
  });

  it("approves on a retry after a failure, and tells the dashboard exactly once", async () => {
    const moved = await proposeRefund();
    nextStream([], "reject");
    await act(async () => seen.latest!.approve("act_1"));
    expect(turnFor("act_1")?.error).toBeTruthy();
    nextStream(executed);
    await act(async () => seen.latest!.approve("act_1"));
    const turn = turnFor("act_1");
    expect(turn?.decided).toBe("approved");
    expect(turn?.error).toBeUndefined();
    expect(seen.latest!.turns.at(-1)?.text).toBe("Refunded $45.00.");
    expect(moved).toHaveBeenCalledTimes(1);
  });
});
