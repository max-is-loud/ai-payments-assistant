import type { HourTotals } from "../../api/types";
import { formatUsd } from "../../lib/money";
import { emptyHourly, formatHour, hourlyView } from "../../lib/series";
import { Axis, Bars } from "../charts/Bars";
import { RailSection } from "./RailSection";

// Today's takings by hour in ink bars. Before the series arrives the bars sit
// at their 2px floor and the note is withheld rather than claiming a quiet day.
export function HourlySection({ hourly }: { hourly: HourTotals[] | null }) {
  const view = hourlyView(hourly ?? emptyHourly());
  return (
    <RailSection title="Today by hour" note={hourly ? view.note : undefined}>
      <Bars
        values={view.hours.map((h) => h.succeeded_total_cents)}
        tone="ink"
        size="rail"
        titles={view.hours.map((h) => `${formatHour(h.hour)}: ${formatUsd(h.succeeded_total_cents)}`)}
      />
      <Axis labels={view.labels} />
    </RailSection>
  );
}
