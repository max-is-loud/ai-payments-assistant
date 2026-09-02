export type AgentEvent = { type: "planning" | "action" | "observation" | "confirmation" | "answer" | "clarify" | "error"; data: Record<string, any> };
export interface TrailProps { events: AgentEvent[] }
export function Trail(p: TrailProps): JSX.Element | null;