export interface BarsProps { values: number[]; max?: number; tone?: "" | "in" | "ink"; size?: "" | "sm" | "rail"; height?: number; titles?: string[] }
export function Bars(p: BarsProps): JSX.Element;
export interface AxisProps { labels: string[]; lastTone?: "" | "in"; xs?: boolean }
export function Axis(p: AxisProps): JSX.Element;