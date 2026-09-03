import type { ComparedPeriod, Comparison } from "../lib/comparison";
import { addDays, dateRangeLabel, weekdayInitial } from "../lib/dates";
import { formatMoney } from "../lib/money";
import { useCurrency } from "../state/useCurrency";
import { Axis, Bars } from "./charts/Bars";
import { Eyebrow } from "./Eyebrow";
import { Figure } from "./Figure";

function weekdays(period: ComparedPeriod): string {
  return period.daily.map((_, i) => weekdayInitial(addDays(period.start, i))).join(" ");
}

function Period({ period, tone, max }: { period: ComparedPeriod; tone: "" | "in"; max: number }) {
  const currency = useCurrency();
  return (
    <div>
      <Eyebrow tone={tone}>{dateRangeLabel(period.start, period.end)}</Eyebrow>
      <div className="total">
        <Figure cents={period.totalCents} size="md" tone={tone} />
        <span className="count">· {period.count}</span>
      </div>
      <Bars values={period.daily} max={max} size="sm" tone={tone} titles={period.daily.map((c) => formatMoney(c, currency))} />
    </div>
  );
}

// Two periods side by side inside an answer: the earlier one as the muted
// baseline, the later one in green, both on one scale so heights compare.
export function ComparisonChart({ comparison }: { comparison: Comparison }) {
  const { earlier, later } = comparison;
  const max = Math.max(...earlier.daily, ...later.daily, 1);
  return (
    <>
      <div className="ldg-compare">
        <Period period={earlier} tone="" max={max} />
        <Period period={later} tone="in" max={max} />
      </div>
      <Axis xs labels={[weekdays(earlier), weekdays(later)]} />
    </>
  );
}
