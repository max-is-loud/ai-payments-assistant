import type { HourTotals } from "../../api/types";
import { formatMoney } from "../../lib/money";
import { useCurrency } from "../../state/useCurrency";
import { emptyHourly, formatHour, hourlyView } from "../../lib/series";
import { Axis, Bars } from "../charts/Bars";
import { RailSection } from "./RailSection";

// Today's takings by hour in ink bars. Before the series arrives the bars sit
// at their 2px floor and the note is withheld rather than claiming a quiet day.
export function HourlySection({ hourly }: { hourly: HourTotals[] | null }) {
  const currency = useCurrency();
  const view = hourlyView(hourly ?? emptyHourly(), currency);
  return (
    <RailSection title="Today by hour" note={hourly ? view.note : undefined}>
      <Bars
        values={view.hours.map((h) => h.succeeded_total_cents)}
        tone="ink"
        size="rail"
        titles={view.hours.map((h) => `${formatHour(h.hour)}: ${formatMoney(h.succeeded_total_cents, currency)}`)}
      />
      <Axis labels={view.labels} />
    </RailSection>
  );
}
