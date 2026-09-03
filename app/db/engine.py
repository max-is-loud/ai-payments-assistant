"""Engine construction and the session context manager."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.models import Base

SQLITE_PREFIX = "sqlite:///"


def make_engine(database_url: str) -> Engine:
    """Create the engine, its parent directory, and every table.

    Two processes (API and bot) share the file, so WAL mode and a busy
    timeout are set on every connection.
    """
    if database_url.startswith(SQLITE_PREFIX) and not database_url.endswith(":memory:"):
        Path(database_url.removeprefix(SQLITE_PREFIX)).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection: Any, _record: Any) -> None:
        """Enable concurrent readers alongside one writer."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    _create_schema(engine)
    _add_missing_columns(engine)
    return engine


def _create_schema(engine: Engine, attempts: int = 3) -> None:
    """Create every table, tolerating another process doing the same at the same moment.

    The API and the bot start together and both call this on one file. On a
    fresh clone that file is empty — the seed never touches it — so the
    reviewer's first `make dev` is a race. `create_all` checks each table and
    then creates it; when the other process creates one inside that gap, the
    CREATE fails with "already exists". The next attempt checks again, finds
    the table, and skips it.

    Raises:
        OperationalError: Any failure other than that collision, or the
            collision persisting past `attempts`.
    """
    for attempt in range(attempts):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError as exc:
            if "already exists" not in str(exc) or attempt == attempts - 1:
                raise


# Columns added after a database file may already have been created. `create_all`
# creates missing tables but never alters existing ones, so each is added here.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("pending_actions", "idempotency_key", "VARCHAR(64)"),
    ("pending_actions", "claimed_at", "DATETIME"),
)


def _add_missing_columns(engine: Engine) -> None:
    """Add the columns in `_ADDED_COLUMNS` that an older database file lacks.

    A reviewer's fresh clone never needs this; a local file from before the
    column existed does. The API and the bot may both attempt it on the same
    file at the same instant, so the loser's "duplicate column" is tolerated.

    Raises:
        OperationalError: Any failure other than that collision.
    """
    inspector = inspect(engine)
    for table, column, kind in _ADDED_COLUMNS:
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        except OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A transaction: commit on success, roll back on any exception."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
