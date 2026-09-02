import React from "react";
const STAMP = { planning: ["PLAN", ""], action: ["ACT", "act"], observation: ["OBS", ""], confirmation: ["ASK", "ask"], clarify: ["ASK", "ask"], error: ["ERR", "err"] };
/** Agent activity list. events: [{type, data}] — same shape as the API's SSE events. Kept verbatim from v1. */
export function Trail({ events = [] }) {
  const shown = events.filter((e) => e.type !== "answer" && e.type !== "clarify");
  if (!shown.length) return null;
  return (
    <ul className="ldg-trail" aria-label="Agent activity">
      {shown.map((e, i) => {
        const failed = e.type === "observation" && e.data.result && e.data.result.error;
        const [label, cls] = failed ? STAMP.error : STAMP[e.type];
        return (
          <li key={i}>
            <span className={"stamp " + cls}>{label}</span>
            <div className="line">
              {e.type === "planning" && String(e.data.reasoning)}
              {e.type === "action" && <><span className="ldg-mono">{e.data.name}</span> {JSON.stringify(e.data.args)}</>}
              {e.type === "observation" && (failed
                ? <><span className="ldg-mono">{e.data.name}</span> failed: {e.data.result.error}{e.data.result.hint ? " — " + e.data.result.hint : ""}</>
                : <details><summary>{e.data.name} returned</summary><pre>{JSON.stringify(e.data.result, null, 2)}</pre></details>)}
              {e.type === "confirmation" && "Waiting for your approval"}
              {e.type === "error" && <>{String(e.data.message)}{e.data.hint ? " — " + e.data.hint : ""}</>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}