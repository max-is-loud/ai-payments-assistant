"""One clock for the database layer."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time as naive UTC.

    SQLite has no timezone type and SQLAlchemy hands back naive datetimes, so
    the whole DB layer stores and compares naive UTC rather than mixing.
    """
    return datetime.now(UTC).replace(tzinfo=None)
