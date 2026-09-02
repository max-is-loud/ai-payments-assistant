/** @startingPoint section="Ledger" subtitle="Money figure in mono" viewport="400x120" */
export interface FigureProps { cents: number; size?: "xl" | "lg" | "md" | "sm"; tone?: "" | "in" | "out"; sign?: string; splitCents?: boolean }
export function Figure(p: FigureProps): JSX.Element;