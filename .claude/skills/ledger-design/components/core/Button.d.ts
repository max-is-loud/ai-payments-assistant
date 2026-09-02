/** @startingPoint section="Ledger" subtitle="Pill buttons" viewport="400x120" */
export interface ButtonProps { variant?: "primary" | "secondary" | "danger"; block?: boolean; size?: "" | "lg"; disabled?: boolean; onClick?: () => void; type?: "button" | "submit"; children: React.ReactNode }
export function Button(p: ButtonProps): JSX.Element;