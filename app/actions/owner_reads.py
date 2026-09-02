"""Read-only owner actions. Every number returned is computed here, not by the model."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.actions.context import OwnerContext
from app.agent.events import to_jsonable
from app.agent.schema import NoParams
from app.db import escalations
from app.domain.models import Invoice, Payment
from app.domain.periods import date_range_window
from app.domain.series import DayTotals, daily_totals
from app.domain.summary import DailyFacts, build_daily_facts, period_totals


class QueryPaymentsParams(BaseModel):
    """Filters for a payment query; all optional."""

    start_date: date | None = Field(None, description="First day, inclusive")
    end_date: date | None = Field(None, description="Last day, inclusive")
    customer_id: str | None = Field(None, description="cus_... to restrict to one customer")
    status: Literal["succeeded", "failed", "refunded", "partially_refunded"] | None = None
    limit: int = Field(
        20,
        ge=1,
        le=100,
        description=(
            "Max payments to list, default 20, up to 100; totals cover every match. "
            "Raise it when the user asks for all of them"
        ),
    )


class FindCustomerParams(BaseModel):
    """Free-text customer lookup."""

    query: str = Field(..., description="Part of a name, email, or a cus_ id")


class ListInvoicesParams(BaseModel):
    """Invoice filters."""

    customer_id: str | None = None
    status: Literal["draft", "open", "paid", "void", "uncollectible"] | None = None


def _payment_row(p: Payment) -> dict[str, Any]:
    """The fields the planner needs to reason and to reference a payment later."""
    return {
        "id": p.id, "customer_id": p.customer_id, "customer_name": p.customer_name,
        "amount_cents": p.amount_cents, "amount_refunded_cents": p.amount_refunded_cents,
        "status": p.status, "failure_reason": p.failure_reason, "description": p.description,
        "occurred_at": p.occurred_at.isoformat(),
    }


def _invoice_row(i: Invoice) -> dict[str, Any]:
    """Invoice fields for the planner and the result cards."""
    return {
        "id": i.id,
        "number": i.number,
        "customer_id": i.customer_id,
        "customer_name": i.customer_name,
        "total_cents": i.total_cents,
        "amount_remaining_cents": i.amount_remaining_cents,
        "status": i.status,
        "due_date": i.due_at.date().isoformat() if i.due_at else None,
        "hosted_url": i.hosted_url,
        "description": i.description,
    }


def summarize_day(ctx: OwnerContext, _params: NoParams) -> DailyFacts:
    """Today's facts versus yesterday, plus open invoices."""
    return build_daily_facts(
        ctx.gateway.list_payments(),
        ctx.gateway.list_invoices(status="open"),
        ctx.now,
    )


def query_payments(ctx: OwnerContext, params: QueryPaymentsParams) -> dict[str, Any]:
    """Payments matching the filters, newest first, with totals over every match.

    Args:
        ctx: Owner context with gateway access.
        params: Payment filters and limits.

    Returns:
        Dictionary with period label, totals over every match, and the first
        `limit` rows. `matched_count` and `listed_count` differ when the list
        is cut short, so the planner can say so or ask for more instead of
        presenting a partial list as complete. With a date range, `daily_totals`
        adds one zero-filled entry per day so the web app can draw the period.
    """
    payments = ctx.gateway.list_payments()
    if params.customer_id:
        payments = [p for p in payments if p.customer_id == params.customer_id]
    if params.status:
        payments = [p for p in payments if p.status == params.status]
    label = "all time"
    daily: list[DayTotals] | None = None
    if params.start_date or params.end_date:
        start = params.start_date or date(2000, 1, 1)
        end = params.end_date or ctx.now.date()
        window = date_range_window(start, end, ctx.now.tzinfo)
        payments = [p for p in payments if window.contains(p.occurred_at)]
        label = window.label
        totals = period_totals(payments, window)
        daily = daily_totals(payments, window)
    else:
        totals = None
    succeeded = [p for p in payments if p.status != "failed"]
    result: dict[str, Any] = {
        "period": label,
        "succeeded_count": (
            totals.succeeded_count if totals else len(succeeded)
        ),
        "succeeded_total_cents": (
            totals.succeeded_total_cents
            if totals
            else sum(p.amount_cents for p in succeeded)
        ),
        "refunded_total_cents": sum(p.amount_refunded_cents for p in succeeded),
        "declined_count": len(
            [p for p in payments if p.status == "failed"]
        ),
        "matched_count": len(payments),
        "listed_count": min(len(payments), params.limit),
        "payments": [_payment_row(p) for p in payments[: params.limit]],
    }
    if daily is not None:
        result["daily_totals"] = to_jsonable(daily)
    return result


def find_customer(ctx: OwnerContext, params: FindCustomerParams) -> dict[str, Any]:
    """Case-insensitive substring match over name, email, and id.

    Args:
        ctx: Owner context with gateway access.
        params: Search query.

    Returns:
        List of matching customer objects and count.
    """
    needle = params.query.strip().lower()
    matches = [
        c for c in ctx.gateway.list_customers()
        if needle in c.name.lower() or needle in (c.email or "").lower() or needle == c.id.lower()
    ]
    return {"matches": [to_jsonable(c) for c in matches], "count": len(matches)}


def list_invoices(ctx: OwnerContext, params: ListInvoicesParams) -> dict[str, Any]:
    """Invoices with optional customer/status filters.

    Args:
        ctx: Owner context with gateway access.
        params: Filters by customer or status.

    Returns:
        List of invoice rows and count.
    """
    invoices = ctx.gateway.list_invoices(customer_id=params.customer_id, status=params.status)
    return {"count": len(invoices), "invoices": [_invoice_row(i) for i in invoices]}


def list_escalations(ctx: OwnerContext, _params: NoParams) -> dict[str, Any]:
    """Pending customer requests awaiting the owner.

    Args:
        ctx: Owner context with database session.
        _params: Unused.

    Returns:
        List of pending escalations and count.
    """
    rows = escalations.pending(ctx.session)
    return {
        "count": len(rows),
        "escalations": [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "invoice_id": r.invoice_id,
                "amount_cents": r.amount_cents,
                "reason": r.reason,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
