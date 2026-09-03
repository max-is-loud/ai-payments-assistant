"""Proposed mutations awaiting approval.

A row moves `pending → executing → executed | failed | needs_review`, or
`pending → cancelled`. `claim` is the safety-critical function: it flips `pending →
executing` in a single conditional UPDATE and stores the idempotency key the
execution will carry, so two concurrent approvals cannot both proceed and a
retry or a recovery sends Stripe the same key the first attempt did.
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


def claim(session: Session, action_id: str, *, idempotency_key: str) -> bool:
    """Atomically move a pending action to executing, recording its key. False if not pending.

    The key is written in the same statement as the status so there is never
    an executing row without one: whatever finishes this execution, now or
    after a crash, reads the key back from the row rather than minting another.
    """
    result = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "pending")
        .values(status="executing", idempotency_key=idempotency_key, claimed_at=utcnow())
    )
    return result.rowcount == 1


def finish(session: Session, action_id: str, result: Any) -> bool:
    """Move an executing action to executed with its result. False if it was not executing."""
    outcome = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "executing")
        .values(
            status="executed", result_json=json.dumps(result, default=str), executed_at=utcnow()
        )
    )
    return outcome.rowcount == 1


def fail(session: Session, action_id: str, error: str) -> bool:
    """Record that execution raised after the claim; the action is not re-approvable."""
    outcome = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "executing")
        .values(status="failed", result_json=json.dumps({"error": error}), executed_at=utcnow())
    )
    return outcome.rowcount == 1


def park_for_review(session: Session, action_id: str, note: dict[str, Any]) -> bool:
    """Move an executing action to needs_review with what a person needs to check it.

    Used when an interrupted execution is too old to finish under its key:
    the note carries the key and the reason, so the owner can look the key
    up in Stripe's request log and settle by hand what happened.
    """
    outcome = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "executing")
        .values(status="needs_review", result_json=json.dumps(note), executed_at=utcnow())
    )
    return outcome.rowcount == 1


def cancel(session: Session, action_id: str, *, actor: str) -> bool:
    """Dismiss a pending action proposed by `actor`. False if decided already or not theirs.

    An action id is not authority on its own: a Telegram callback or an API
    body can carry any id, so the row is dismissed only for the actor whose
    proposal it is.
    """
    result = session.execute(
        update(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.actor == actor,
            PendingAction.status == "pending",
        )
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


def executing(session: Session, channel: str) -> list[PendingAction]:
    """Rows a process of this channel was executing when it stopped, oldest first.

    Each channel runs in its own process (the API for web, the bot for
    Telegram), so at that process's startup every executing row of its channel
    is by definition interrupted, and it is the one that can finish them.
    """
    return list(session.scalars(
        select(PendingAction)
        .where(PendingAction.channel == channel, PendingAction.status == "executing")
        .order_by(PendingAction.created_at)
    ).all())
