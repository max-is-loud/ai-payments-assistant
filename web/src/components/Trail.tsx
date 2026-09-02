import type { JSX } from "react";
import type { AgentEvent } from "../api/types";

const STAMP: Record<AgentEvent["type"], { label: string; cls: string }> = {
  planning: { label: "PLAN", cls: "" }, action: { label: "ACT", cls: "act" }, observation: { label: "OBS", cls: "" },
  confirmation: { label: "ASK", cls: "ask" }, answer: { label: "SAY", cls: "" }, clarify: { label: "ASK", cls: "ask" },
  error: { label: "ERR", cls: "err" },
};

// An action that failed inside a turn arrives as an observation whose result is
// {error, hint} — the shape the loop feeds back to the model. The owner should
// read it as a sentence, not as the JSON block a successful result gets.
type Failure = { error: string; hint?: string };

function failure(result: unknown): Failure | null {
  if (typeof result !== "object" || result === null || !("error" in result)) return null;
  return result as Failure;
}

function withHint(text: string, hint: unknown): string {
  return hint ? `${text} — ${String(hint)}` : text;
}

function line(event: AgentEvent): JSX.Element {
  const d = event.data;
  switch (event.type) {
    case "planning": return <span>{String(d.reasoning)}</span>;
    case "action": return <span><span className="mono">{String(d.name)}</span> {JSON.stringify(d.args)}</span>;
    case "observation": {
      const failed = failure(d.result);
      if (failed) return <span><span className="mono">{String(d.name)}</span> failed: {withHint(failed.error, failed.hint)}</span>;
      return (
        <details><summary>{String(d.name)} returned</summary><pre className="mono">{JSON.stringify(d.result, null, 2)}</pre></details>
      );
    }
    case "confirmation": return <span>Waiting for your approval</span>;
    // `detail` is only present when the API runs with DEBUG=1; the server decides.
    case "error": return (
      <>
        <span>{withHint(String(d.message), d.hint)}</span>
        {d.detail ? <pre className="mono">{String(d.detail)}</pre> : null}
      </>
    );
    default: return <span />;
  }
}

function stamp(event: AgentEvent): { label: string; cls: string } {
  return event.type === "observation" && failure(event.data.result) ? STAMP.error : STAMP[event.type];
}

export function Trail({ events }: { events: AgentEvent[] }) {
  const shown = events.filter((e) => e.type !== "answer" && e.type !== "clarify");
  if (!shown.length) return null;
  return (
    <ul className="trail" aria-label="Agent activity">
      {shown.map((e, i) => (
        <li key={i}>
          <span className={`stamp ${stamp(e).cls}`}>{stamp(e).label}</span>
          <div className="line">{line(e)}</div>
        </li>
      ))}
    </ul>
  );
}
