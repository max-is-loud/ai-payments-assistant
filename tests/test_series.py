"""The chart series are computed in Python, bucketed by the owner's local day and hour."""

from datetime import UTC, date, datetime, timedelta, timezone

from app.domain.models import Payment
from app.domain.periods import date_range_window
from app.domain.series import CustomerTotals, DayTotals, HourTotals, build_series, daily_totals

TZ = timezone(timedelta(hours=-4))
NOW = datetime(2026, 9, 1, 15, 0, tzinfo=TZ)


def _payment(
    amount: int, when: datetime, status: str = "succeeded", name: str | None = "Acme Corp"
) -> Payment:
    """A payment with only the fields the series read varied."""
    return Payment(
        id=f"pi_{amount}_{when.timestamp()}", charge_id="ch", customer_id="cus", customer_name=name,
        amount_cents=amount, amount_refunded_cents=0, status=status,  # type: ignore[arg-type]
        failure_reason=None, description=None, occurred_at=when,
    )


def test_daily_totals_zero_fill_every_day_oldest_first() -> None:
    """A quiet day still gets an entry, so bars line up with dates; declines never count."""
    window = date_range_window(date(2026, 8, 30), date(2026, 9, 1), TZ)
    payments = [
        _payment(1000, NOW), _payment(2500, NOW), _payment(700, NOW - timedelta(days=2)),
        _payment(9999, NOW, status="failed"), _payment(5, NOW - timedelta(days=3)),
    ]
    assert daily_totals(payments, window) == [
        DayTotals("2026-08-30", 700, 1),
        DayTotals("2026-08-31", 0, 0),
        DayTotals("2026-09-01", 3500, 2),
    ]


def test_daily_totals_bucket_by_the_local_day_not_utc() -> None:
    """23:30 local on Aug 31 is already Sep 1 in UTC; the owner's day wins."""
    late = datetime(2026, 8, 31, 23, 30, tzinfo=TZ).astimezone(UTC)
    window = date_range_window(date(2026, 8, 31), date(2026, 9, 1), TZ)
    assert [d.succeeded_count for d in daily_totals([_payment(100, late)], window)] == [1, 0]


def test_series_covers_three_weeks_ending_today() -> None:
    """21 days of history plus today: the window the seed populates."""
    series = build_series([_payment(100, NOW)], NOW)
    assert len(series.daily) == 22
    assert series.daily[0].date == "2026-08-11"
    assert series.daily[-1] == DayTotals("2026-09-01", 100, 1)


def test_hourly_today_has_all_24_local_hours_and_ignores_other_days() -> None:
    """Every hour is returned because today's seeded payments land at whatever hour the seed ran."""
    payments = [
        _payment(100, NOW), _payment(250, NOW.replace(hour=9)),
        _payment(9, NOW - timedelta(days=1)),
    ]
    hourly = build_series(payments, NOW).hourly_today
    assert [h.hour for h in hourly] == list(range(24))
    assert hourly[15] == HourTotals(15, 100, 1)
    assert hourly[9] == HourTotals(9, 250, 1)
    assert sum(h.succeeded_count for h in hourly) == 2


def test_top_customers_rank_succeeded_totals_inside_the_window() -> None:
    """Ranked by money taken over the three weeks; declines and older history do not count."""
    payments = [
        _payment(100, NOW, name="Maya Chen"), _payment(300, NOW, name="Acme Corp"),
        _payment(50, NOW, name="Maya Chen"), _payment(999, NOW, status="failed", name="Doyle Ltd"),
        _payment(5000, NOW - timedelta(days=40), name="Old Co"),
    ]
    assert build_series(payments, NOW).top_customers == [
        CustomerTotals("Acme Corp", 300, 1), CustomerTotals("Maya Chen", 150, 2),
    ]


def test_top_customers_stop_at_five() -> None:
    """The rail has room for five rows."""
    payments = [_payment(100 * (i + 1), NOW, name=f"C{i}") for i in range(7)]
    names = [c.customer_name for c in build_series(payments, NOW).top_customers]
    assert names == ["C6", "C5", "C4", "C3", "C2"]
