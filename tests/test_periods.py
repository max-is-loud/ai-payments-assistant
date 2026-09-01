"""Day boundaries are computed in one place and in the local timezone."""

from datetime import date, datetime, timedelta, timezone

from app.domain.periods import date_range_window, day_window, today_window, yesterday_window

TZ = timezone(timedelta(hours=-4))


def test_day_window_spans_local_midnight_to_midnight() -> None:
    """A day runs from local 00:00 inclusive to the next local 00:00 exclusive."""
    window = day_window(date(2026, 9, 1), TZ)
    assert window.start == datetime(2026, 9, 1, 0, 0, tzinfo=TZ)
    assert window.end == datetime(2026, 9, 2, 0, 0, tzinfo=TZ)
    assert window.contains(datetime(2026, 9, 1, 23, 59, tzinfo=TZ))
    assert not window.contains(datetime(2026, 9, 2, 0, 0, tzinfo=TZ))


def test_today_and_yesterday_follow_now() -> None:
    """Today and yesterday are derived from the supplied clock, not the wall clock."""
    now = datetime(2026, 9, 1, 10, 0, tzinfo=TZ)
    assert today_window(now).start.date() == date(2026, 9, 1)
    assert yesterday_window(now).start.date() == date(2026, 8, 31)
    assert yesterday_window(now).end == today_window(now).start


def test_date_range_is_end_inclusive() -> None:
    """Natural-language ranges ("Aug 24 to Aug 30") include the last day."""
    window = date_range_window(date(2026, 8, 24), date(2026, 8, 30), TZ)
    assert window.end == datetime(2026, 8, 31, 0, 0, tzinfo=TZ)
    assert window.label == "2026-08-24 to 2026-08-30"
