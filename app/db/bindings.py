"""Telegram identity bindings and their lifecycle (bind, renew, expire, revoke)."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import TelegramBinding
from app.domain.policy import BINDING_INACTIVITY


def bind(
    session: Session, *, telegram_id: int, customer_id: str, customer_name: str, now: datetime
) -> TelegramBinding:
    """Create or replace the binding for a Telegram account (a re-bind supersedes)."""
    row = session.get(TelegramBinding, telegram_id)
    if row is None:
        row = TelegramBinding(telegram_id=telegram_id, stripe_customer_id=customer_id,
                              customer_name=customer_name, bound_at=now, last_seen_at=now)
        session.add(row)
    else:
        row.stripe_customer_id = customer_id
        row.customer_name = customer_name
        row.bound_at = now
        row.last_seen_at = now
        row.revoked_at = None
    session.flush()
    return row


def resolve(session: Session, telegram_id: int, now: datetime) -> TelegramBinding | None:
    """The active binding for a Telegram account, renewing its activity window.

    An idle binding past `BINDING_INACTIVITY` is revoked here, on first
    contact after expiry, so nothing needs a background job.
    """
    row = session.get(TelegramBinding, telegram_id)
    if row is None or row.revoked_at is not None:
        return None
    if now - row.last_seen_at > BINDING_INACTIVITY:
        row.revoked_at = now
        session.flush()
        return None
    row.last_seen_at = now
    session.flush()
    return row


def revoke(session: Session, telegram_id: int, now: datetime) -> bool:
    """Customer-side `/logout`."""
    result = session.execute(
        update(TelegramBinding)
        .where(TelegramBinding.telegram_id == telegram_id, TelegramBinding.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount == 1


def revoke_for_customer(session: Session, customer_id: str, now: datetime) -> int:
    """Owner-side revocation of every device bound to a customer."""
    result = session.execute(
        update(TelegramBinding)
        .where(
            TelegramBinding.stripe_customer_id == customer_id,
            TelegramBinding.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    return result.rowcount


def active_for_customer(session: Session, customer_id: str) -> TelegramBinding | None:
    """Where to notify a customer, if they are bound anywhere."""
    return session.scalars(
        select(TelegramBinding)
        .where(
            TelegramBinding.stripe_customer_id == customer_id,
            TelegramBinding.revoked_at.is_(None),
        )
        .order_by(TelegramBinding.last_seen_at.desc())
        .limit(1)
    ).first()
