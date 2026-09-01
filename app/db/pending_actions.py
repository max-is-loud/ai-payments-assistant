"""Proposed mutations awaiting approval.

`claim` is the safety-critical function: it flips `pending → executed` in a
single conditional UPDATE, so two concurrent approvals cannot both proceed.
"""

import json
import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.clock import utcnow
from app.db.models import PendingAction


def new_action_id() -> str:
    """Short, unguessable id shown in the UI, e.g. `act_7f3a9c1d`."""
    return f"act_{secrets.token_hex(4)}"


def create(
    session: Session,
    *,
    conversation_id: str,
    channel: str,
    actor: str,
    action: str,
    parameters: dict[str, Any],
    summary: str,
    prompt: str,
) -> PendingAction:
    """Store a fully resolved proposal."""
    row = PendingAction(
        id=new_action_id(), conversation_id=conversation_id, channel=channel, actor=actor,
        action=action, parameters_json=json.dumps(parameters, default=str), summary=summary,
        prompt=prompt, status="pending", created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def get(session: Session, action_id: str) -> PendingAction | None:
    """Lookup by id."""
    return session.get(PendingAction, action_id)


def claim(session: Session, action_id: str) -> bool:
    """Atomically move a pending action to executed. False if it was not pending."""
    result = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "pending")
        .values(status="executed", executed_at=utcnow())
    )
    return result.rowcount == 1


def finish(session: Session, action_id: str, result: Any) -> None:
    """Attach the execution result for the history view."""
    session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id)
        .values(result_json=json.dumps(result, default=str))
    )


def cancel(session: Session, action_id: str) -> bool:
    """Dismiss a pending action. False if it had already been decided."""
    result = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "pending")
        .values(status="cancelled", executed_at=utcnow())
    )
    return result.rowcount == 1


def latest_pending(session: Session, conversation_id: str) -> PendingAction | None:
    """The proposal a reloaded UI should still show, if any."""
    return session.scalars(
        select(PendingAction)
        .where(PendingAction.conversation_id == conversation_id, PendingAction.status == "pending")
        .order_by(PendingAction.created_at.desc())
        .limit(1)
    ).first()


def fail(session: Session, action_id: str, error: str) -> None:
    """Record that execution raised after the claim; the action is not re-approvable."""
    session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id)
        .values(status="failed", result_json=json.dumps({"error": error}))
    )
