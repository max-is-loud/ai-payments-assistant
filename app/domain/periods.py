"""Time windows for "today", "yesterday", and explicit date ranges.

All boundaries are local-midnight in the given timezone (default: the
machine's), so the reviewer's day is the reviewer's day.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo


@dataclass(frozen=True)
class Window:
    """A half-open interval [start, end) with a human label."""

    start: datetime
    end: datetime
    label: str

    def contains(self, moment: datetime) -> bool:
        """Whether a tz-aware moment falls inside the window."""
        return self.start <= moment < self.end


def local_timezone() -> tzinfo:
    """The process's local timezone, resolved once per call from the system clock."""
    tz = datetime.now().astimezone().tzinfo
    assert tz is not None  # astimezone() always attaches one
    return tz


def day_window(day: date, tz: tzinfo | None = None) -> Window:
    """The local calendar day containing `day`."""
    zone = tz or local_timezone()
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    return Window(start=start, end=start + timedelta(days=1), label=day.isoformat())


def today_window(now: datetime | None = None) -> Window:
    """Today according to `now` (tz-aware) or the local clock."""
    current = now or datetime.now(local_timezone())
    return day_window(current.date(), current.tzinfo)


def yesterday_window(now: datetime | None = None) -> Window:
    """The day before today, sharing today's timezone."""
    current = now or datetime.now(local_timezone())
    return day_window(current.date() - timedelta(days=1), current.tzinfo)


def date_range_window(start: date, end_inclusive: date, tz: tzinfo | None = None) -> Window:
    """A range of whole days, end inclusive, as people phrase ranges."""
    zone = tz or local_timezone()
    first = datetime(start.year, start.month, start.day, tzinfo=zone)
    last = datetime(end_inclusive.year, end_inclusive.month, end_inclusive.day, tzinfo=zone)
    return Window(
        start=first,
        end=last + timedelta(days=1),
        label=f"{start.isoformat()} to {end_inclusive.isoformat()}",
    )
