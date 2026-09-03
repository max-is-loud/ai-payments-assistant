import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch, describeError, streamTurn } from "../api/client";
import type { AgentEvent, Confirmation, ExecutedResult, HistoryResponse } from "../api/types";

// A confirmation's state: approving while the request is in flight, approved
// only once the server streamed the executed result, cancelled by the owner.
export type Decision = "approving" | "approved" | "cancelled";

export interface Turn {
  id: string;
  role: "user" | "assistant";
  text?: string;
  events: AgentEvent[];
  confirmation?: Confirmation;
  decided?: Decision;
  result?: ExecutedResult;
  error?: string;
}

// An SSE error frame, read the same way an HTTP error envelope is.
function describeFrame(data: Record<string, unknown>): string {
  return describeError(new ApiError(
    0, String(data.code ?? "error"), String(data.message ?? "The approval did not complete."),
    String(data.hint ?? ""), String(data.detail ?? ""),
  ));
}

const KEY = "ledger.conversation";

function conversationId(): string {
  try {
    const existing = localStorage.getItem(KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    localStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

export function useConversation() {
  const id = useRef(conversationId());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mutationListeners = useRef<(() => void)[]>([]);

  const onMutation = useCallback((cb: () => void) => {
    mutationListeners.current.push(cb);
    return () => {
      mutationListeners.current = mutationListeners.current.filter((f) => f !== cb);
    };
  }, []);
  const notifyMutation = () => mutationListeners.current.forEach((cb) => cb());

  const patch = (turnId: string, fn: (t: Turn) => Turn) =>
    setTurns((prev) => prev.map((t) => (t.id === turnId ? fn(t) : t)));

  useEffect(() => {
    apiFetch<HistoryResponse>(`/api/conversations/${id.current}`)
      .then((history) => {
        const restored: Turn[] = history.messages.map((m, i) => ({ id: `h${i}`, role: m.role, text: m.content, events: [] }));
        if (history.pending) restored.push({ id: history.pending.action_id, role: "assistant", events: [], confirmation: history.pending });
        setTurns(restored);
      })
      .catch((e) => setError(describeError(e)));
  }, []);

  // Merge one SSE event into the turn it belongs to. A confirmation event also
  // re-keys the turn's id to the action_id, in the same object, so approve/cancel
  // (which patch by action_id) can find it. Transport-level failures are surfaced
  // separately by the catch blocks in send/approve; SSE error frames only ever
  // render as ERR lines in the Trail.
  const mergeEvent = (t: Turn, event: AgentEvent): Turn => {
    const next: Turn = { ...t, events: [...t.events, event] };
    if (event.type === "answer") { next.text = String(event.data.text); if (event.data.result) next.result = event.data.result as ExecutedResult; }
    if (event.type === "clarify") next.text = String(event.data.question);
    if (event.type === "confirmation") {
      next.confirmation = event.data as unknown as Confirmation;
      next.id = String(event.data.action_id);
    }
    return next;
  };

  // Route one SSE event into the assistant turn being built, via a single dispatch.
  const absorb = (turnId: string, event: AgentEvent) =>
    setTurns((prev) => prev.map((t) => (t.id === turnId ? mergeEvent(t, event) : t)));

  const send = useCallback(async (text: string) => {
    const userId = crypto.randomUUID(), assistantId = crypto.randomUUID();
    setTurns((prev) => [...prev, { id: userId, role: "user", text, events: [] }, { id: assistantId, role: "assistant", events: [] }]);
    setBusy(true); setError(null);
    try {
      await streamTurn(`/api/conversations/${id.current}/messages`, { text }, (e) => absorb(assistantId, e));
    } catch (e) {
      patch(assistantId, (t) => ({ ...t, error: describeError(e) }));
    } finally {
      setBusy(false);
    }
  }, []);

  // Approval is a claim about money. The card says "approved" only once the
  // stream has delivered the executed result; an HTTP failure, or a stream
  // that ends with an error frame instead, puts the card back to its buttons
  // with the failure under it, and the dashboard is told nothing moved. The
  // idempotency key is the server's, stored on the action, so none is sent.
  const approve = useCallback(async (actionId: string) => {
    const resultId = crypto.randomUUID();
    patch(actionId, (t) => ({ ...t, decided: "approving", error: undefined }));
    setTurns((prev) => [...prev, { id: resultId, role: "assistant", events: [] }]);
    setBusy(true);
    let executed = false;
    let failure: string | undefined;
    try {
      await streamTurn(`/api/conversations/${id.current}/confirm`, { action_id: actionId }, (e) => {
        absorb(resultId, e);
        if (e.type === "answer" && e.data.result) executed = true;
        if (e.type === "error") failure = describeFrame(e.data);
      });
    } catch (e) {
      failure = describeError(e);
    } finally {
      setBusy(false);
    }
    if (executed) {
      patch(actionId, (t) => ({ ...t, decided: "approved" }));
      notifyMutation();
      return;
    }
    setTurns((prev) => prev.filter((t) => t.id !== resultId));
    patch(actionId, (t) => ({ ...t, decided: undefined, error: failure ?? "The approval did not complete." }));
  }, []);

  const cancel = useCallback(async (actionId: string) => {
    try {
      await apiFetch(`/api/conversations/${id.current}/cancel`, { method: "POST", body: JSON.stringify({ action_id: actionId }) });
      patch(actionId, (t) => ({ ...t, decided: "cancelled" }));
    } catch (e) {
      setError(describeError(e));
    }
  }, []);

  return { turns, busy, error, send, approve, cancel, onMutation };
}
