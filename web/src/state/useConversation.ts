import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch, streamTurn } from "../api/client";
import type { AgentEvent, Confirmation, ExecutedResult, HistoryResponse } from "../api/types";

export interface Turn {
  id: string;
  role: "user" | "assistant";
  text?: string;
  events: AgentEvent[];
  confirmation?: Confirmation;
  decided?: "approved" | "cancelled";
  result?: ExecutedResult;
  error?: string;
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

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.hint ? `${error.message} ${error.hint}` : error.message;
  return error instanceof Error ? error.message : String(error);
}

export function useConversation() {
  const id = useRef(conversationId());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mutationListeners = useRef<(() => void)[]>([]);

  const onMutation = useCallback((cb: () => void) => { mutationListeners.current.push(cb); }, []);
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
      .catch((e) => setError(describe(e)));
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
      patch(assistantId, (t) => ({ ...t, error: describe(e) }));
    } finally {
      setBusy(false);
    }
  }, []);

  const approve = useCallback(async (actionId: string) => {
    const resultId = crypto.randomUUID();
    patch(actionId, (t) => ({ ...t, decided: "approved" }));
    setTurns((prev) => [...prev, { id: resultId, role: "assistant", events: [] }]);
    setBusy(true);
    try {
      await streamTurn(`/api/conversations/${id.current}/confirm`, { action_id: actionId },
        (e) => absorb(resultId, e), { "Idempotency-Key": actionId });
      notifyMutation();
    } catch (e) {
      patch(resultId, (t) => ({ ...t, error: describe(e) }));
    } finally {
      setBusy(false);
    }
  }, []);

  const cancel = useCallback(async (actionId: string) => {
    try {
      await apiFetch(`/api/conversations/${id.current}/cancel`, { method: "POST", body: JSON.stringify({ action_id: actionId }) });
      patch(actionId, (t) => ({ ...t, decided: "cancelled" }));
    } catch (e) {
      setError(describe(e));
    }
  }, []);

  return { turns, busy, error, send, approve, cancel, onMutation };
}
