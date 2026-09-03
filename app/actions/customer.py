"""Everything the customer bot can do, scoped to the bound customer.

No action here takes a customer id; the gateway in the context is already
bound. The $2,000 ceiling is enforced in `_guard_ceiling`, called by both
the proposal and the execution path, before any payment call.
"""

from datetime import UTC
from typing import Any

from pydantic import Field

from app.actions.context import CustomerContext
from app.agent.executor import ActionError
from app.agent.schema import (
    DISPLAY_KEY,
    INTERNAL,
    ActionSpec,
    NoParams,
    Proposal,
    Registry,
    StrictParams,
)
from app.db import escalations
from app.domain.models import Invoice
from app.domain.money import format_money
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS

CEILING_MESSAGE = (
    "This invoice is above the amount I can take here, so I've asked the business owner to "
    "approve it. You'll get a payment link in this chat once they do."
)
APPROVED_MESSAGE = (
    "The business owner has approved this invoice and the payment link was sent to this "
    "chat; I can't take the payment here myself."
)


def _needs_owner(invoice: Invoice) -> bool:
    """Whether the ceiling applies: the amount still owed is at or above it."""
    return invoice.amount_remaining_cents >= TELEGRAM_PAYMENT_CEILING_CENTS


def _invoice_row(invoice: Invoice) -> dict[str, Any]:
    """An invoice as the customer planner sees it: no amounts, and a link only where it may pay.

    Stripe's hosted invoice page takes payment, so below the ceiling it is the
    "View" link and above it it is a way around the owner's approval. At or
    above the ceiling the row carries no URL, in any status, so nothing
    downstream (the planner's text, a button, a callback) can hand it over
    before the owner approves; the approval path sends it itself.
    """
    needs_owner = _needs_owner(invoice)
    return {
        "invoice_id": invoice.id,
        "number": invoice.number,
        "status": invoice.status,
        "due_date": invoice.due_at.date().isoformat() if invoice.due_at else None,
        "description": invoice.description,
        "view_url": None if needs_owner else invoice.hosted_url,
        "requires_owner_approval": needs_owner,
    }


def _amounts_for_display(ctx: CustomerContext, invoices: list[Invoice]) -> dict[str, str]:
    """The amount still owed on each open invoice, formatted, keyed by invoice id.

    Placed under `DISPLAY_KEY`, which the loop strips from what the planner
    reads: the renderer writes these figures onto the buttons, so the customer
    sees what they owe while the model can neither restate nor misstate it.
    """
    currency = ctx.gateway.default_currency()
    return {
        i.id: format_money(i.amount_remaining_cents, currency)
        for i in invoices if i.status == "open" and i.amount_remaining_cents > 0
    }


def my_balance(ctx: CustomerContext, _params: NoParams) -> dict[str, Any]:
    """How many invoices are unpaid and when the next is due; the figures ride under `display`."""
    unpaid = [i for i in ctx.gateway.my_invoices(status="open") if i.amount_remaining_cents > 0]
    due_dates = sorted(i.due_at for i in unpaid if i.due_at)
    owed = sum(i.amount_remaining_cents for i in unpaid)
    return {
        "unpaid_count": len(unpaid),
        "overdue_count": len([i for i in unpaid if i.due_at and i.due_at < ctx.now]),
        "next_due_date": due_dates[0].date().isoformat() if due_dates else None,
        "invoices": [_invoice_row(i) for i in unpaid],
        DISPLAY_KEY: {
            "invoice_amounts": _amounts_for_display(ctx, unpaid),
            "owed_total": format_money(owed, ctx.gateway.default_currency()),
        },
    }


def my_invoices(ctx: CustomerContext, _params: NoParams) -> dict[str, Any]:
    """Every invoice on the account, open first; the open amounts ride under `display`."""
    invoices = sorted(
        ctx.gateway.my_invoices(),
        key=lambda i: (i.status != "open", i.occurred_at),
        reverse=False,
    )
    return {
        "count": len(invoices),
        "invoices": [_invoice_row(i) for i in invoices],
        DISPLAY_KEY: {"invoice_amounts": _amounts_for_display(ctx, invoices)},
    }


class PayInvoiceParams(StrictParams):
    """Pay one of the customer's own invoices.

    `expected_amount_cents` is set by the server when the payment is proposed:
    the amount owed at that moment, which is what the confirmation names.
    Approval pays only if that is still the amount owed. The planner never
    sees the field.
    """

    invoice_id: str = Field(..., description="invoice_id from my_balance or my_invoices")
    expected_amount_cents: int | None = Field(None, json_schema_extra=INTERNAL)


def _payable(ctx: CustomerContext, invoice_id: str) -> Invoice:
    """Resolve an invoice the customer owns and can still pay.

    Raises:
        ActionError: Not open, or nothing remaining.
        NotYourInvoice: Propagates from the scoped gateway.
    """
    invoice = ctx.gateway.my_invoice(invoice_id)
    if invoice.status != "open" or invoice.amount_remaining_cents <= 0:
        msg = (
            f"Invoice {invoice.number or invoice.id} is {invoice.status}; "
            "nothing to pay."
        )
        raise ActionError(msg)
    return invoice


def _guard_ceiling(ctx: CustomerContext, invoice: Invoice) -> dict[str, Any] | None:
    """File an escalation and return it when the invoice is at or above the ceiling.

    Reuses the escalation already filed for the same invoice, pending or
    approved, so repeated attempts neither pile up on the owner's panel nor
    re-ask a question the owner has answered. Returns None when the invoice is
    payable here.
    """
    if not _needs_owner(invoice):
        return None
    row = escalations.for_invoice(ctx.session, ctx.telegram_id, invoice.id)
    if row is None:
        row = escalations.file(
            ctx.session, telegram_id=ctx.telegram_id, customer_id=ctx.gateway.customer_id,
            customer_name=ctx.customer_name, invoice_id=invoice.id,
            amount_cents=invoice.amount_remaining_cents,
            reason="Payment at or above the bot's limit",
            now=ctx.now.astimezone(UTC).replace(tzinfo=None),
        )
    message = APPROVED_MESSAGE if row.status == "approved" else CEILING_MESSAGE
    return {"escalated": True, "escalation_id": row.id, "message": message}


def describe_pay_invoice(ctx: CustomerContext, params: PayInvoiceParams) -> Proposal:
    """Either a confirmation with the amount, or an escalation instead of a confirmation."""
    invoice = _payable(ctx, params.invoice_id)
    escalated = _guard_ceiling(ctx, invoice)
    if escalated:
        return Proposal(resolved=escalated)
    summary = (
        f"Pay invoice {invoice.number or invoice.id} for "
        f"{format_money(invoice.amount_remaining_cents, ctx.gateway.default_currency())} "
        "with your card on file"
    )
    return Proposal(
        summary=summary,
        params=PayInvoiceParams(
            invoice_id=invoice.id, expected_amount_cents=invoice.amount_remaining_cents
        ),
    )


def pay_invoice(ctx: CustomerContext, params: PayInvoiceParams) -> dict[str, Any]:
    """Charge the card on file. The ceiling is re-checked here; this path is what approval runs.

    When recovering an interrupted execution the invoice may already be paid
    by the attempt that died, so only ownership is checked before the call;
    Stripe replays that payment under the stored key.

    Raises:
        ActionError: At or above the ceiling (after filing the escalation), or
            the amount owed is no longer the one the customer confirmed.
    """
    if ctx.recovering:
        invoice = ctx.gateway.my_invoice(params.invoice_id)
    else:
        invoice = _payable(ctx, params.invoice_id)
        expected = params.expected_amount_cents
        if expected is not None and invoice.amount_remaining_cents != expected:
            raise ActionError(
                "The amount owed on this invoice has changed since you confirmed. "
                "Tap Pay again to see the current amount."
            )
    escalated = _guard_ceiling(ctx, invoice)
    if escalated:
        raise ActionError(escalated["message"])
    paid = ctx.gateway.pay_my_invoice(params.invoice_id, idempotency_key=ctx.idempotency_key or "")
    return {
        "paid": True, "invoice_id": paid.id, "number": paid.number,
        "amount_cents": paid.total_cents, "receipt_url": paid.hosted_url,
    }


class EscalateParams(StrictParams):
    """Hand something the bot cannot do to the owner."""

    reason: str = Field(
        ...,
        min_length=1,
        description="What the customer is asking for, in their words",
    )


def escalate_to_owner(ctx: CustomerContext, params: EscalateParams) -> dict[str, Any]:
    """File a general escalation (disputes, questions, anything outside paying invoices)."""
    row = escalations.file(
        ctx.session, telegram_id=ctx.telegram_id, customer_id=ctx.gateway.customer_id,
        customer_name=ctx.customer_name, invoice_id=None, amount_cents=0, reason=params.reason,
        now=ctx.now.astimezone(UTC).replace(tzinfo=None),
    )
    return {"escalated": True, "escalation_id": row.id,
            "message": "I've passed this to the business owner; they'll follow up here."}


def build_customer_registry() -> Registry:
    """The bot's action set. Note what is absent: any way to name another customer."""
    return Registry([
        ActionSpec(
            "my_balance",
            "How many invoices the customer has unpaid and when the next is due",
            NoParams,
            my_balance,
        ),
        ActionSpec(
            "my_invoices",
            "The customer's invoices with links to view each one",
            NoParams,
            my_invoices,
        ),
        ActionSpec(
            "pay_invoice",
            "Pay one of the customer's open invoices with their card on file "
            "(asks for confirmation)",
            PayInvoiceParams,
            pay_invoice,
            mutation=True,
            describe=describe_pay_invoice,
        ),
        ActionSpec(
            "escalate_to_owner",
            "Hand a request the bot cannot fulfil to the business owner",
            EscalateParams,
            escalate_to_owner,
        ),
    ])
