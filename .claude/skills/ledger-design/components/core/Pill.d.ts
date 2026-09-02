export interface PillProps { tone?: "neutral" | "in" | "out" | "wait"; solid?: boolean; children: React.ReactNode }
export function Pill(p: PillProps): JSX.Element;