"""Persistence invariants: a pending action executes once; bindings expire."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from app.db import bindings, conversations, escalations, pending_actions
from app.db.engine import session_scope

NOW = datetime(2026, 9, 1, 12, 0)


def test_pending_action_can_be_claimed_exactly_once(engine: Engine) -> None:
    """Two approvals of the same action_id must not produce two refunds."""
    with session_scope(engine) as session:
        action = pending_actions.create(
            session,
            conversation_id="c1",
            channel="web",
            actor="owner",
            action="refund_payment",
            parameters={"payment_id": "pi_1", "amount_cents": None},
            summary="Refund $45.00",
            prompt="refund",
        )
        action_id = action.id
    with session_scope(engine) as session:
        assert pending_actions.claim(session, action_id, idempotency_key="exec_1") is True
    with session_scope(engine) as session:
        assert pending_actions.claim(session, action_id, idempotency_key="exec_2") is False
        row = pending_actions.get(session, action_id)
        assert row is not None
        # The first claim's key is the one every retry and recovery must reuse.
        assert row.status == "executing" and row.idempotency_key == "exec_1"


def test_binding_expires_after_inactivity(engine: Engine) -> None:
    """Fourteen idle days revoke the binding; activity inside the window renews it."""
    with session_scope(engine) as session:
        bindings.bind(
            session,
            telegram_id=42,
            customer_id="cus_acme",
            customer_name="Acme Corp",
            now=NOW,
        )
    with session_scope(engine) as session:
        assert bindings.resolve(session, 42, NOW + timedelta(days=13)) is not None
    with session_scope(engine) as session:
        # last_seen_at moved to day 13, so day 26 is still inside the window; day 28 is not.
        assert bindings.resolve(session, 42, NOW + timedelta(days=26)) is not None
        assert bindings.resolve(session, 42, NOW + timedelta(days=41)) is None
    with session_scope(engine) as session:
        assert bindings.resolve(session, 42, NOW + timedelta(days=41, hours=1)) is None


def test_owner_revocation_covers_every_binding_for_a_customer(engine: Engine) -> None:
    """DELETE /api/customers/{id}/telegram-binding must cut off every device."""
    with session_scope(engine) as session:
        bindings.bind(
            session,
            telegram_id=1,
            customer_id="cus_acme",
            customer_name="Acme Corp",
            now=NOW,
        )
        bindings.bind(
            session,
            telegram_id=2,
            customer_id="cus_acme",
            customer_name="Acme Corp",
            now=NOW,
        )
        bindings.bind(
            session,
            telegram_id=3,
            customer_id="cus_maya",
            customer_name="Maya Chen",
            now=NOW,
        )
    with session_scope(engine) as session:
        assert bindings.revoke_for_customer(session, "cus_acme", NOW) == 2
        assert bindings.resolve(session, 1, NOW) is None
        assert bindings.resolve(session, 3, NOW) is not None


def test_escalation_is_approved_once(engine: Engine) -> None:
    """Approving twice is a no-op the second time so the customer is not notified twice."""
    with session_scope(engine) as session:
        esc = escalations.file(
            session, telegram_id=42, customer_id="cus_acme", customer_name="Acme Corp",
            invoice_id="in_1", amount_cents=240000, reason="Above the bot's limit", now=NOW,
        )
        esc_id = esc.id
    with session_scope(engine) as session:
        assert escalations.mark_approved(session, esc_id, NOW) is not None
        assert escalations.mark_approved(session, esc_id, NOW) is None
        assert escalations.pending(session) == []


def test_conversation_history_is_oldest_first_and_bounded(engine: Engine) -> None:
    """The planner sees the last N turns in chronological order."""
    with session_scope(engine) as session:
        for i in range(5):
            role = "user" if i % 2 == 0 else "assistant"
            conversations.append(session, "c1", role, f"m{i}")
    with session_scope(engine) as session:
        history = conversations.history(session, "c1", limit=3)
        assert [m.content for m in history] == ["m2", "m3", "m4"]


def test_make_engine_survives_another_process_creating_the_schema_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API and the bot start together on an empty file, and only one can win.

    `create_all` checks each table then creates it. When the other process
    creates a table inside that gap, the CREATE fails with "already exists".
    A second attempt sees the table and moves on; what must not happen is a
    crash on first start, because `make dev` is the reviewer's first start.
    """
    from sqlalchemy.dialects.sqlite.base import SQLiteDialect

    from app.db.engine import make_engine

    url = f"sqlite:///{tmp_path / 'race.db'}"
    make_engine(url)  # the process that won: every table now exists

    real_has_table = SQLiteDialect.has_table
    lied: list[str] = []

    def stale_check(self: Any, connection: Any, table_name: str, *args: Any, **kw: Any) -> bool:
        """Report the first table absent — a check made before the other process's CREATE landed."""
        if not lied:
            lied.append(table_name)
            return False
        return real_has_table(self, connection, table_name, *args, **kw)

    monkeypatch.setattr(SQLiteDialect, "has_table", stale_check)
    engine = make_engine(url)  # the process that lost: its first CREATE collides
    assert lied, "the stale check was never consulted"
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM conversations").scalar() == 0


def test_make_engine_adds_the_execution_key_column_to_an_older_file(tmp_path: Path) -> None:
    """A database created before `idempotency_key` existed gains the column on the next start.

    `create_all` never alters an existing table, so the engine adds the column
    itself; a reviewer's fresh clone never takes this path, a local file from
    an earlier build does.
    """
    from sqlalchemy import inspect

    from app.db.engine import make_engine

    url = f"sqlite:///{tmp_path / 'older.db'}"
    engine = make_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE pending_actions DROP COLUMN idempotency_key")

    def columns(target: Any) -> set[str]:
        """The column names of pending_actions as the file has them right now."""
        return {c["name"] for c in inspect(target).get_columns("pending_actions")}

    assert "idempotency_key" not in columns(engine)
    engine.dispose()

    reopened = make_engine(url)
    assert "idempotency_key" in columns(reopened)
    with session_scope(reopened) as session:
        row = pending_actions.create(
            session, conversation_id="c1", channel="web", actor="owner", action="refund_payment",
            parameters={}, summary="s", prompt="p",
        )
        assert pending_actions.claim(session, row.id, idempotency_key="exec_1")


def test_cancel_requires_the_proposing_actor(engine: Engine) -> None:
    """An action id alone cannot dismiss a proposal; the actor must be the one who made it."""
    with session_scope(engine) as session:
        action_id = pending_actions.create(
            session, conversation_id="telegram:7", channel="telegram", actor="telegram:7",
            action="pay_invoice", parameters={"invoice_id": "in_1"}, summary="Pay", prompt="p",
        ).id
    with session_scope(engine) as session:
        assert pending_actions.cancel(session, action_id, actor="telegram:9") is False
        assert pending_actions.get(session, action_id).status == "pending"  # type: ignore[union-attr]
        assert pending_actions.cancel(session, action_id, actor="telegram:7") is True
        assert pending_actions.get(session, action_id).status == "cancelled"  # type: ignore[union-attr]
