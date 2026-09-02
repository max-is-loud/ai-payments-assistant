// Mini bar chart. Heights are percentages of `max` (the largest value unless
// a shared scale is passed in); the stylesheet keeps every bar at least 2px so
// a day with nothing still reads as a day.
export function Bars({ values, max, tone = "", size = "", titles = [] }: {
  values: number[];
  max?: number;
  tone?: "" | "in" | "ink";
  size?: "" | "sm" | "rail";
  titles?: string[];
}) {
  const top = max ?? Math.max(...values, 1);
  return (
    <div className={["ldg-bars", size].filter(Boolean).join(" ")}>
      {values.map((value, i) => (
        <i key={i} className={tone} title={titles[i]} style={{ height: `${top > 0 ? (value / top) * 100 : 0}%` }} />
      ))}
    </div>
  );
}

// Axis row under a chart; the last label may be highlighted (green "Today").
export function Axis({ labels, lastTone = "", xs = false }: {
  labels: string[];
  lastTone?: "" | "in";
  xs?: boolean;
}) {
  return (
    <div className={["ldg-axis", xs ? "xs" : ""].filter(Boolean).join(" ")}>
      {labels.map((label, i) => (
        <span key={i} className={i === labels.length - 1 ? lastTone : ""}>{label}</span>
      ))}
    </div>
  );
}
