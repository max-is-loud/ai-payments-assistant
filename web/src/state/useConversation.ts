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

  // Route one SSE event into the assistant turn being built.
  const absorb = (turnId: string, event: AgentEvent) =>
    patch(turnId, (t) => {
      const next: Turn = { ...t, events: [...t.events, event] };
      if (event.type === "answer") { next.text = String(event.data.text); if (event.data.result) next.result = event.data.result as ExecutedResult; }
      if (event.type === "clarify") next.text = String(event.data.question);
      if (event.type === "confirmation") {
        next.confirmation = event.data as unknown as Confirmation;
        setTurns((prev) => prev.map((t2) => (t2.id === turnId ? { ...t2, id: String(event.data.action_id) } : t2)));
      }
      if (event.type === "error" && !event.data.recoverable) next.error = String(event.data.message);
      return next;
    });

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
