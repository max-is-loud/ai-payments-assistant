"""Per-day, per-hour, and per-customer revenue series for the owner app's charts.

Like `summary.py`, these are deterministic facts: computed in Python from the
payment list and narrated by nobody. Days and hours are bucketed in the
timezone of the `now` passed in, which is the owner's local clock, so a
payment at 23:30 local still belongs to the local day once UTC has rolled over.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.models import Payment
from app.domain.periods import Window, date_range_window, today_window

# Days of history before today. The seed writes exactly this much
# (`seed.dataset.HISTORY_DAYS`), so the trend shows every day that exists.
TREND_DAYS = 21
# Rows in the rail's ranked list; the design has room for five.
TOP_CUSTOMERS = 5


@dataclass(frozen=True)
class DayTotals:
    """Money taken on one local calendar day. `date` is ISO so it sorts and serialises as-is."""

    date: str
    succeeded_total_cents: int
    succeeded_count: int


@dataclass(frozen=True)
class HourTotals:
    """Money taken during one local hour of today; `hour` runs 0–23."""

    hour: int
    succeeded_total_cents: int
    succeeded_count: int


@dataclass(frozen=True)
class CustomerTotals:
    """Money taken from one customer over the trend window."""

    customer_name: str
    succeeded_total_cents: int
    succeeded_count: int


@dataclass(frozen=True)
class Series:
    """Everything the charts draw, in one round trip."""

    daily: list[DayTotals]
    hourly_today: list[HourTotals]
    top_customers: list[CustomerTotals]


class _Tally:
    """Running total and count for one bucket of payments."""

    def __init__(self) -> None:
        """Start empty."""
        self.total = 0
        self.count = 0

    def add(self, cents: int) -> None:
        """Count one more payment of `cents`."""
        self.total += cents
        self.count += 1


def _revenue_inside(payments: Sequence[Payment], window: Window) -> list[Payment]:
    """Payments that count as money taken in the window.

    Declines are excluded; refunds are not netted, matching `summary.period_totals`
    so the hero figure and the chart agree.
    """
    return [p for p in payments if p.status != "failed" and window.contains(p.occurred_at)]


def trend_window(now: datetime) -> Window:
    """The last `TREND_DAYS` days plus today, in `now`'s timezone."""
    today = now.date()
    return date_range_window(today - timedelta(days=TREND_DAYS), today, now.tzinfo)


def daily_totals(payments: Sequence[Payment], window: Window) -> list[DayTotals]:
    """One entry per local calendar day in the window, oldest first.

    Days with nothing taken are present with zeros so a chart's bars line up
    with its dates without the caller filling gaps.
    """
    tz = window.start.tzinfo
    buckets: defaultdict[str, _Tally] = defaultdict(_Tally)
    for p in _revenue_inside(payments, window):
        buckets[p.occurred_at.astimezone(tz).date().isoformat()].add(p.amount_cents)
    # Same tzinfo on both sides, so this is whole wall-clock days even across DST.
    day_count = (window.end - window.start).days
    days = ((window.start + timedelta(days=i)).date().isoformat() for i in range(day_count))
    return [DayTotals(day, buckets[day].total, buckets[day].count) for day in days]


def _hourly_today(payments: Sequence[Payment], now: datetime) -> list[HourTotals]:
    """Today's takings by local hour, all 24 of them.

    Seeded payments for today carry Stripe's real timestamp, which is whatever
    hour the reviewer ran the seed, so the chart cannot assume business hours.
    """
    buckets: defaultdict[int, _Tally] = defaultdict(_Tally)
    for p in _revenue_inside(payments, today_window(now)):
        buckets[p.occurred_at.astimezone(now.tzinfo).hour].add(p.amount_cents)
    return [HourTotals(hour, buckets[hour].total, buckets[hour].count) for hour in range(24)]


def _top_customers(payments: Sequence[Payment], window: Window) -> list[CustomerTotals]:
    """Customers ranked by money taken in the window, best first, capped for the rail."""
    buckets: defaultdict[str, _Tally] = defaultdict(_Tally)
    for p in _revenue_inside(payments, window):
        buckets[p.customer_name or "Unknown customer"].add(p.amount_cents)
    ranked = sorted(buckets.items(), key=lambda item: item[1].total, reverse=True)
    return [
        CustomerTotals(name, tally.total, tally.count) for name, tally in ranked[:TOP_CUSTOMERS]
    ]


def build_series(payments: Sequence[Payment], now: datetime) -> Series:
    """Assemble the three series over the trend window ending today."""
    window = trend_window(now)
    return Series(
        daily=daily_totals(payments, window),
        hourly_today=_hourly_today(payments, now),
        top_customers=_top_customers(payments, window),
    )
