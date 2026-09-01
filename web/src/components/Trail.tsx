import type { JSX } from "react";
import type { AgentEvent } from "../api/types";

const STAMP: Record<AgentEvent["type"], { label: string; cls: string }> = {
  planning: { label: "PLAN", cls: "" }, action: { label: "ACT", cls: "act" }, observation: { label: "OBS", cls: "" },
  confirmation: { label: "ASK", cls: "ask" }, answer: { label: "SAY", cls: "" }, clarify: { label: "ASK", cls: "ask" },
  error: { label: "ERR", cls: "err" },
};

function line(event: AgentEvent): JSX.Element {
  const d = event.data;
  switch (event.type) {
    case "planning": return <span>{String(d.reasoning)}</span>;
    case "action": return <span><span className="mono">{String(d.name)}</span> {JSON.stringify(d.args)}</span>;
    case "observation": return (
      <details><summary>{String(d.name)} returned</summary><pre className="mono">{JSON.stringify(d.result, null, 2)}</pre></details>
    );
    case "confirmation": return <span>Waiting for your approval</span>;
    case "error": return <span>{String(d.message)}{d.hint ? ` — ${String(d.hint)}` : ""}</span>;
    default: return <span />;
  }
}

export function Trail({ events }: { events: AgentEvent[] }) {
  const shown = events.filter((e) => e.type !== "answer" && e.type !== "clarify");
  if (!shown.length) return null;
  return (
    <ul className="trail" aria-label="Agent activity">
      {shown.map((e, i) => (
        <li key={i}>
          <span className={`stamp ${STAMP[e.type].cls}`}>{STAMP[e.type].label}</span>
          <div className="line">{line(e)}</div>
        </li>
      ))}
    </ul>
  );
}
