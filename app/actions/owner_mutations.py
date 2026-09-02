"""Owner actions that change Stripe or approve an escalation.

Each has a `describe_*` that resolves ids into a sentence for the
confirmation card and validates what Stripe would otherwise reject later,
and a handler that executes with the injected idempotency key.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.actions.context import OwnerContext
from app.actions.owner_reads import _invoice_row
from app.agent.executor import ActionError
from app.agent.schema import Proposal, ProposalDetails
from app.db import escalations
from app.domain.money import format_usd
from app.services.escalations import EscalationNotFound, approve_and_notify


def _key(ctx: OwnerContext) -> str:
    """The idempotency key execute_pending injected; empty only in direct tests."""
    return ctx.idempotency_key or ""


class RefundParams(BaseModel):
    """Refund a payment fully or partially."""

    payment_id: str = Field(..., description="pi_... from query_payments")
    amount_cents: int | None = Field(None, gt=0, description="Omit to refund the remaining balance")


def _paid_when(occurred_at: datetime, now: datetime) -> str:
    """"paid today at 09:14" or "paid Aug 25 at 09:14", on the owner's clock."""
    local = occurred_at.astimezone(now.tzinfo)
    day = "today" if local.date() == now.date() else f"{local:%b %d}"
    return f"paid {day} at {local:%H:%M}"


def describe_refund(ctx: OwnerContext, params: RefundParams) -> Proposal:
    """Resolve the payment and check the amount before asking for approval.

    Args:
        ctx: Owner context with gateway access.
        params: The payment and optional amount to refund.

    Returns:
        A proposal describing the refund, with the resolved amount as details.

    Raises:
        ActionError: Not refundable, or more than the refundable balance.
    """
    payment = ctx.gateway.get_payment(params.payment_id)
    if payment.status == "failed" or payment.refundable_cents == 0:
        raise ActionError(f"{params.payment_id} has nothing refundable (status {payment.status}).")
    amount = payment.refundable_cents if params.amount_cents is None else params.amount_cents
    if amount > payment.refundable_cents:
        raise ActionError(
            f"Only {format_usd(payment.refundable_cents)} is refundable on {params.payment_id}."
        )
    who = payment.customer_name or "the customer"
    meta = " · ".join(
        part for part in (payment.description, payment.id, _paid_when(payment.occurred_at, ctx.now))
        if part
    )
    return Proposal(
        summary=(
            f"Refund {format_usd(amount)} to {who} — {format_usd(payment.amount_cents)} payment "
            f"from {payment.occurred_at:%b %d}"
        ),
        details=ProposalDetails(amount_cents=amount, counterparty=payment.customer_name, meta=meta),
    )


def refund_payment(ctx: OwnerContext, params: RefundParams) -> dict[str, Any]:
    """Execute the refund.

    Args:
        ctx: Owner context with gateway and idempotency key.
        params: The payment and optional amount to refund.

    Returns:
        Refund result with id, amount, and status.
    """
    payment = ctx.gateway.get_payment(params.payment_id)
    refund = ctx.gateway.refund(
        params.payment_id, params.amount_cents, idempotency_key=_key(ctx)
    )
    return {
        "refund_id": refund.id,
        "payment_id": params.payment_id,
        "amount_cents": refund.amount_cents,
        "customer_name": payment.customer_name,
        "status": refund.status,
    }


class CreateInvoiceParams(BaseModel):
    """Create a send-by-email invoice with one line."""

    customer_id: str = Field(..., description="cus_... from find_customer")
    amount_cents: int = Field(..., gt=0)
    description: str = Field(..., min_length=1, description="Line item text")
    due_date: date = Field(..., description="YYYY-MM-DD, after today")


def describe_create_invoice(ctx: OwnerContext, params: CreateInvoiceParams) -> Proposal:
    """Resolve the customer name and check the due date.

    Args:
        ctx: Owner context with gateway and current time.
        params: Invoice details and due date.

    Returns:
        A proposal describing the invoice, with the customer and due date as details.

    Raises:
        ActionError: Due date is today or earlier.
    """
    if params.due_date <= ctx.now.date():
        raise ActionError("The due date must be in the future.")
    customer = ctx.gateway.get_customer(params.customer_id)
    return Proposal(
        summary=(
            f"Create a {format_usd(params.amount_cents)} invoice for {customer.name} due "
            f"{params.due_date:%a %b %d, %Y} — {params.description}"
        ),
        details=ProposalDetails(
            amount_cents=params.amount_cents, counterparty=customer.name,
            meta=f"{params.description} · due {params.due_date:%a %b %d}",
        ),
    )


def create_invoice(ctx: OwnerContext, params: CreateInvoiceParams) -> dict[str, Any]:
    """Create and finalise the invoice.

    Args:
        ctx: Owner context with gateway and idempotency key.
        params: Invoice details.

    Returns:
        The created invoice as a row dictionary.
    """
    invoice = ctx.gateway.create_invoice(
        customer_id=params.customer_id, amount_cents=params.amount_cents,
        description=params.description, due_date=params.due_date, idempotency_key=_key(ctx),
    )
    return _invoice_row(invoice)


class PaymentLinkParams(BaseModel):
    """A one-off Stripe payment link."""

    amount_cents: int = Field(..., gt=0)
    description: str = Field(..., min_length=1, description="What is being paid for")


def describe_payment_link(_ctx: OwnerContext, params: PaymentLinkParams) -> Proposal:
    """Nothing to resolve; state the amount and purpose.

    Args:
        _ctx: Owner context (unused).
        params: Amount and description.

    Returns:
        A proposal describing the payment link; there is no counterparty yet.
    """
    summary = (
        f"Create a payment link for {format_usd(params.amount_cents)} — "
        f"{params.description}"
    )
    return Proposal(
        summary=summary,
        details=ProposalDetails(
            amount_cents=params.amount_cents, counterparty=None, meta=params.description
        ),
    )


def create_payment_link(ctx: OwnerContext, params: PaymentLinkParams) -> dict[str, Any]:
    """Create the link.

    Args:
        ctx: Owner context with gateway and idempotency key.
        params: Amount and description.

    Returns:
        The payment link URL and parameters.
    """
    url = ctx.gateway.create_payment_link(
        amount_cents=params.amount_cents, description=params.description, idempotency_key=_key(ctx)
    )
    return {"url": url, "amount_cents": params.amount_cents, "description": params.description}


class ApproveEscalationParams(BaseModel):
    """Approve a customer's escalated request."""

    escalation_id: str = Field(..., description="esc_... from list_escalations")


def describe_approve_escalation(ctx: OwnerContext, params: ApproveEscalationParams) -> Proposal:
    """Name the customer and amount being approved.

    Args:
        ctx: Owner context with database session.
        params: The escalation id to approve.

    Returns:
        A proposal describing the approval and what approving does.

    Raises:
        ActionError: Unknown or already decided.
    """
    row = escalations.get(ctx.session, params.escalation_id)
    if row is None or row.status != "pending":
        raise ActionError(f"No pending escalation {params.escalation_id}.")
    summary = (
        f"Approve {row.customer_name}'s request to pay "
        f"{format_usd(row.amount_cents)} and send them the payment link on Telegram"
    )
    return Proposal(
        summary=summary,
        details=ProposalDetails(
            amount_cents=row.amount_cents, counterparty=row.customer_name,
            meta="Sends a Stripe payment link on Telegram",
        ),
    )


def approve_escalation(ctx: OwnerContext, params: ApproveEscalationParams) -> dict[str, Any]:
    """Approve and notify via the shared service.

    Args:
        ctx: Owner context with gateway, session, and notifier.
        params: The escalation id to approve.

    Returns:
        An approval outcome as a dictionary.

    Raises:
        ActionError: Unknown escalation.
    """
    try:
        outcome = approve_and_notify(
            ctx.session, params.escalation_id, gateway=ctx.gateway, notify=ctx.notify, now=ctx.now
        )
    except EscalationNotFound as exc:
        raise ActionError(f"No escalation {params.escalation_id}.") from exc
    return outcome.__dict__.copy()
