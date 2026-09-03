"""Everything the customer bot can do, scoped to the bound customer.

No action here takes a customer id; the gateway in the context is already
bound. The $2,000 ceiling is enforced in `_guard_ceiling`, called by both
the proposal and the execution path, before any payment call.
"""

from datetime import UTC
from typing import Any

from pydantic import BaseModel, Field

from app.actions.context import CustomerContext
from app.agent.executor import ActionError
from app.agent.schema import ActionSpec, NoParams, Proposal, Registry
from app.db import escalations
from app.domain.models import Invoice
from app.domain.money import format_money
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS

CEILING_MESSAGE = (
    "This invoice is above the amount I can take here, so I've asked the business owner to "
    "approve it. You'll get a payment link in this chat once they do."
)


def _invoice_row(invoice: Invoice) -> dict[str, Any]:
    """An invoice as the customer planner sees it: no amounts, a link to view them."""
    return {
        "invoice_id": invoice.id,
        "number": invoice.number,
        "status": invoice.status,
        "due_date": invoice.due_at.date().isoformat() if invoice.due_at else None,
        "description": invoice.description,
        "view_url": invoice.hosted_url,
    }


def my_balance(ctx: CustomerContext, _params: NoParams) -> dict[str, Any]:
    """How many invoices are unpaid and when the next is due."""
    unpaid = [i for i in ctx.gateway.my_invoices(status="open") if i.amount_remaining_cents > 0]
    due_dates = sorted(i.due_at for i in unpaid if i.due_at)
    return {
        "unpaid_count": len(unpaid),
        "overdue_count": len([i for i in unpaid if i.due_at and i.due_at < ctx.now]),
        "next_due_date": due_dates[0].date().isoformat() if due_dates else None,
        "invoices": [_invoice_row(i) for i in unpaid],
    }


def my_invoices(ctx: CustomerContext, _params: NoParams) -> dict[str, Any]:
    """Every invoice on the account, open first."""
    invoices = sorted(
        ctx.gateway.my_invoices(),
        key=lambda i: (i.status != "open", i.occurred_at),
        reverse=False,
    )
    return {"count": len(invoices), "invoices": [_invoice_row(i) for i in invoices]}


class PayInvoiceParams(BaseModel):
    """Pay one of the customer's own invoices."""

    invoice_id: str = Field(..., description="invoice_id from my_balance or my_invoices")


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

    Reuses a pending escalation for the same invoice so repeated attempts do
    not pile up on the owner's panel. Returns None when the invoice is payable.
    """
    if invoice.amount_remaining_cents < TELEGRAM_PAYMENT_CEILING_CENTS:
        return None
    existing = next(
        (e for e in escalations.pending(ctx.session)
         if e.telegram_id == ctx.telegram_id and e.invoice_id == invoice.id),
        None,
    )
    row = existing or escalations.file(
        ctx.session, telegram_id=ctx.telegram_id, customer_id=ctx.gateway.customer_id,
        customer_name=ctx.customer_name, invoice_id=invoice.id,
        amount_cents=invoice.amount_remaining_cents, reason="Payment at or above the bot's limit",
        now=ctx.now.astimezone(UTC).replace(tzinfo=None),
    )
    return {"escalated": True, "escalation_id": row.id, "message": CEILING_MESSAGE}


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
    return Proposal(summary=summary)


def pay_invoice(ctx: CustomerContext, params: PayInvoiceParams) -> dict[str, Any]:
    """Charge the card on file. The ceiling is re-checked here; this path is what approval runs.

    Raises:
        ActionError: At or above the ceiling (after filing the escalation).
    """
    invoice = _payable(ctx, params.invoice_id)
    if _guard_ceiling(ctx, invoice):
        raise ActionError(CEILING_MESSAGE)
    paid = ctx.gateway.pay_my_invoice(params.invoice_id, idempotency_key=ctx.idempotency_key or "")
    return {
        "paid": True, "invoice_id": paid.id, "number": paid.number,
        "amount_cents": paid.total_cents, "receipt_url": paid.hosted_url,
    }


class EscalateParams(BaseModel):
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
