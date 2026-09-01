"""Requests handed from the bot to the owner."""

import secrets
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Escalation


def file(
    session: Session,
    *,
    telegram_id: int,
    customer_id: str,
    customer_name: str,
    invoice_id: str | None,
    amount_cents: int,
    reason: str,
    now: datetime,
) -> Escalation:
    """Record a new pending escalation."""
    row = Escalation(
        id=f"esc_{secrets.token_hex(4)}", telegram_id=telegram_id, stripe_customer_id=customer_id,
        customer_name=customer_name, invoice_id=invoice_id, amount_cents=amount_cents,
        reason=reason, status="pending", created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def pending(session: Session) -> list[Escalation]:
    """Everything awaiting the owner, oldest first."""
    return list(session.scalars(
        select(Escalation).where(Escalation.status == "pending").order_by(Escalation.created_at)
    ).all())


def get(session: Session, escalation_id: str) -> Escalation | None:
    """Lookup by id."""
    return session.get(Escalation, escalation_id)


def mark_approved(session: Session, escalation_id: str, now: datetime) -> Escalation | None:
    """Approve once; returns None when it was not pending so callers do not re-notify."""
    result = session.execute(
        update(Escalation)
        .where(Escalation.id == escalation_id, Escalation.status == "pending")
        .values(status="approved", resolved_at=now)
    )
    if result.rowcount != 1:
        return None
    return session.get(Escalation, escalation_id)
