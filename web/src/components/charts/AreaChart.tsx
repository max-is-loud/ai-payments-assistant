// Full-width area trend. One value per day, oldest first; the last point is
// today and gets the dot. The SVG stretches to the container, so the stroke
// is drawn with a non-scaling vector effect (in the stylesheet) to stay 2px.
const WIDTH = 1000;
const PAD = 12;

export function AreaChart({ values, height = 170, maxLabel }: {
  values: number[];
  height?: number;
  maxLabel?: string;
}) {
  const max = Math.max(...values, 1);
  const steps = Math.max(values.length - 1, 1);
  const points = values.map(
    (v, i) => [(i / steps) * WIDTH, height - PAD - (v / max) * (height - PAD * 2)] as const,
  );
  const line = points.length ? `M${points.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")}` : "";
  const last = points[points.length - 1];
  return (
    <div className="ldg-area" style={{ height }}>
      <div className="grid"><i /><i /><i /><i /></div>
      {maxLabel && <div className="max">{maxLabel}</div>}
      <svg viewBox={`0 0 ${WIDTH} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        {line && <path className="fill" d={`${line} L${WIDTH} ${height} L0 ${height} Z`} />}
        {line && <path className="line" d={line} />}
      </svg>
      {last && <div className="today" style={{ top: `${((last[1] / height) * 100).toFixed(1)}%` }} />}
    </div>
  );
}
