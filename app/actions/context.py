"""What handlers receive. One context type per channel; both carry `idempotency_key`."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.stripe_.customer_client import CustomerScopedGateway
from app.stripe_.gateway import StripeGateway


class Notifier(Protocol):
    """Sends a Telegram message with an optional URL button; True when delivered."""

    def __call__(self, telegram_id: int, text: str, url: str | None) -> bool:
        """Deliver one message to one customer."""
        ...


@dataclass
class OwnerContext:
    """Full-account access for the owner's web assistant."""

    gateway: StripeGateway
    session: Session
    now: datetime
    notify: Notifier
    idempotency_key: str | None = None


@dataclass
class CustomerContext:
    """Access bound to one customer. The gateway cannot be pointed elsewhere."""

    gateway: CustomerScopedGateway
    session: Session
    telegram_id: int
    customer_name: str
    now: datetime
    idempotency_key: str | None = None


def no_notifier(_telegram_id: int, _text: str, _url: str | None) -> bool:
    """Notifier used when no Telegram token is configured: nothing is sent."""
    return False
