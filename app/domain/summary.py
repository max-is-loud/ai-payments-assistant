"""Deterministic facts behind the daily summary.

The LLM narrates these numbers; it never computes them. Everything here is
plain dataclasses so the result can be serialised with `dataclasses.asdict`.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Invoice, Payment
from app.domain.periods import Window, today_window, yesterday_window


@dataclass(frozen=True)
class PeriodTotals:
    """Revenue figures for one window."""

    label: str
    succeeded_count: int
    succeeded_total_cents: int
    refunded_total_cents: int
    declined_count: int
    declined_reasons: dict[str, int]


@dataclass(frozen=True)
class OpenInvoiceFact:
    """An unpaid invoice as the summary mentions it."""

    customer_name: str | None
    number: str | None
    amount_remaining_cents: int
    due_date: str | None
    overdue: bool


@dataclass(frozen=True)
class PaymentFact:
    """A single notable payment."""

    customer_name: str | None
    amount_cents: int
    description: str | None


@dataclass(frozen=True)
class DailyFacts:
    """Everything the narrator may mention about today."""

    today: PeriodTotals
    yesterday: PeriodTotals
    open_invoices: list[OpenInvoiceFact]
    open_invoice_total_cents: int
    largest_payment: PaymentFact | None


def period_totals(payments: Sequence[Payment], window: Window) -> PeriodTotals:
    """Sum a window's payments.

    Refunds are attributed to the day of the original payment, which is the
    simplest rule that keeps "you took $X" and "you refunded $Y" consistent.
    """
    inside = [p for p in payments if window.contains(p.occurred_at)]
    succeeded = [p for p in inside if p.status != "failed"]
    declined = [p for p in inside if p.status == "failed"]
    reasons = Counter(p.failure_reason or "unknown" for p in declined)
    return PeriodTotals(
        label=window.label,
        succeeded_count=len(succeeded),
        succeeded_total_cents=sum(p.amount_cents for p in succeeded),
        refunded_total_cents=sum(p.amount_refunded_cents for p in succeeded),
        declined_count=len(declined),
        declined_reasons=dict(reasons),
    )


def build_daily_facts(
    payments: Sequence[Payment], invoices: Sequence[Invoice], now: datetime
) -> DailyFacts:
    """Assemble today's facts, the comparison with yesterday, and what is still unpaid."""
    today = today_window(now)
    open_invoices = sorted(
        (i for i in invoices if i.status == "open" and i.amount_remaining_cents > 0),
        key=lambda i: i.amount_remaining_cents,
        reverse=True,
    )
    todays_successes = [
        p for p in payments if today.contains(p.occurred_at) and p.status != "failed"
    ]
    largest = max(todays_successes, key=lambda p: p.amount_cents, default=None)
    return DailyFacts(
        today=period_totals(payments, today),
        yesterday=period_totals(payments, yesterday_window(now)),
        open_invoices=[
            OpenInvoiceFact(
                customer_name=i.customer_name,
                number=i.number,
                amount_remaining_cents=i.amount_remaining_cents,
                due_date=i.due_at.date().isoformat() if i.due_at else None,
                overdue=bool(i.due_at and i.due_at < now),
            )
            for i in open_invoices
        ],
        open_invoice_total_cents=sum(i.amount_remaining_cents for i in open_invoices),
        largest_payment=(
            PaymentFact(largest.customer_name, largest.amount_cents, largest.description)
            if largest
            else None
        ),
    )
