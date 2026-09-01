"""Immutable domain records. Amounts are integer cents; times are tz-aware UTC."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PaymentStatus = Literal["succeeded", "failed", "refunded", "partially_refunded"]


@dataclass(frozen=True)
class Customer:
    """A Stripe customer as the assistant refers to it."""

    id: str
    name: str
    email: str | None


@dataclass(frozen=True)
class Payment:
    """One payment attempt, successful or declined.

    `occurred_at` is the business time of the payment. For seeded history it
    is the intended historical moment rather than Stripe's creation time; see
    `app.domain.mapping`.
    """

    id: str
    charge_id: str
    customer_id: str | None
    customer_name: str | None
    amount_cents: int
    amount_refunded_cents: int
    status: PaymentStatus
    failure_reason: str | None
    description: str | None
    occurred_at: datetime

    @property
    def refundable_cents(self) -> int:
        """How much can still be refunded on this payment."""
        return max(self.amount_cents - self.amount_refunded_cents, 0)


@dataclass(frozen=True)
class Invoice:
    """An invoice with the fields both the owner and the customer bot need."""

    id: str
    number: str | None
    customer_id: str
    customer_name: str | None
    total_cents: int
    amount_remaining_cents: int
    status: str
    due_at: datetime | None
    hosted_url: str | None
    description: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class Refund:
    """The receipt returned after a refund executes."""

    id: str
    payment_id: str
    amount_cents: int
    status: str
