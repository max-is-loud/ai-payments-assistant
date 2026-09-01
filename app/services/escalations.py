"""Owner approval of an escalation: mark it, then hand the customer a payment link.

Shared by the chat action `approve_escalation` and `POST /api/escalations/{id}/approve`.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.actions.context import Notifier
from app.db import escalations
from app.stripe_.gateway import StripeGateway


class EscalationNotFound(LookupError):
    """No escalation with that id."""


@dataclass(frozen=True)
class ApprovalOutcome:
    """What happened, in a shape both the chat narrator and the REST route can return."""

    escalation_id: str
    customer_name: str
    amount_cents: int
    invoice_id: str | None
    hosted_url: str | None
    notified: bool
    already_approved: bool


APPROVED_TEXT = (
    "Good news — the business owner approved your request. Tap below to pay securely on Stripe."
)
APPROVED_TEXT_NO_LINK = "The business owner has approved your request and will follow up directly."


def approve_and_notify(
    session: Session, escalation_id: str, *, gateway: StripeGateway, notify: Notifier, now: datetime
) -> ApprovalOutcome:
    """Approve once and notify the customer on Telegram.

    A second approval is a no-op (`already_approved=True`) so a double-click
    or a chat-plus-panel race never messages the customer twice.

    Args:
        session: Database session.
        escalation_id: The escalation to approve.
        gateway: Stripe access to fetch invoice details.
        notify: The Telegram callback.
        now: Current time.

    Returns:
        An outcome describing what happened.

    Raises:
        EscalationNotFound: Unknown id.
    """
    row = escalations.get(session, escalation_id)
    if row is None:
        raise EscalationNotFound(escalation_id)
    approved = escalations.mark_approved(
        session, escalation_id, now.replace(tzinfo=None)
    )
    if approved is None:
        return ApprovalOutcome(
            row.id, row.customer_name, row.amount_cents, row.invoice_id, None, False, True
        )
    hosted_url = (
        gateway.get_invoice(row.invoice_id).hosted_url if row.invoice_id else None
    )
    text = APPROVED_TEXT if hosted_url else APPROVED_TEXT_NO_LINK
    delivered = notify(row.telegram_id, text, hosted_url)
    return ApprovalOutcome(
        row.id,
        row.customer_name,
        row.amount_cents,
        row.invoice_id,
        hosted_url,
        delivered,
        False,
    )
