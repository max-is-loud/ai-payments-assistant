"""The numbers in the daily summary are computed in Python, never by the model."""

from datetime import datetime, timedelta, timezone

from app.domain.models import Invoice, Payment
from app.domain.periods import today_window
from app.domain.summary import build_daily_facts, period_totals

TZ = timezone(timedelta(hours=-4))
NOW = datetime(2026, 9, 1, 15, 0, tzinfo=TZ)


def _payment(
    amount: int, when: datetime, status: str = "succeeded", reason: str | None = None,
    refunded: int = 0, name: str = "Acme Corp",
) -> Payment:
    """A payment with only the fields the summary reads varied."""
    return Payment(
        id=f"pi_{amount}_{when.timestamp()}", charge_id="ch", customer_id="cus", customer_name=name,
        amount_cents=amount, amount_refunded_cents=refunded, status=status,  # type: ignore[arg-type]
        failure_reason=reason, description=None, occurred_at=when,
    )


def _invoice(remaining: int, due: datetime | None, status: str = "open") -> Invoice:
    """An invoice for Acme with a given remaining balance and due date."""
    return Invoice(
        id="in", number="F-1", customer_id="cus", customer_name="Acme Corp", total_cents=remaining,
        amount_remaining_cents=remaining, status=status, due_at=due, hosted_url=None,
        description=None, occurred_at=NOW,
    )


def test_period_totals_counts_only_successes_and_separates_declines() -> None:
    """Declines never inflate revenue; refunds are netted separately."""
    payments = [
        _payment(10000, NOW), _payment(5000, NOW, refunded=5000, status="refunded"),
        _payment(7000, NOW, status="failed", reason="insufficient_funds"),
        _payment(9999, NOW - timedelta(days=1)),
    ]
    totals = period_totals(payments, today_window(NOW))
    assert totals.succeeded_count == 2
    assert totals.succeeded_total_cents == 15000
    assert totals.refunded_total_cents == 5000
    assert totals.declined_count == 1
    assert totals.declined_reasons == {"insufficient_funds": 1}


def test_daily_facts_compare_with_yesterday_and_list_open_invoices() -> None:
    """The example summary needs today, yesterday, declines, and the unpaid Acme invoice."""
    yesterday = NOW - timedelta(days=1)
    payments = [_payment(4280, NOW, name="Maya Chen"), _payment(1000, yesterday)]
    invoices = [
        _invoice(120000, NOW + timedelta(days=10)),
        _invoice(5000, NOW - timedelta(days=2)),
        _invoice(0, None, status="paid"),
    ]
    facts = build_daily_facts(payments, invoices, NOW)
    assert facts.today.succeeded_total_cents == 4280
    assert facts.yesterday.succeeded_total_cents == 1000
    assert [i.amount_remaining_cents for i in facts.open_invoices] == [120000, 5000]
    assert facts.open_invoices[1].overdue is True
    assert facts.open_invoice_total_cents == 125000
    assert facts.largest_payment is not None
    assert facts.largest_payment.customer_name == "Maya Chen"
