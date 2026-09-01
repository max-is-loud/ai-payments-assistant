"""The one concession to a fresh sandbox: occurred_at may come from seed metadata."""

from datetime import UTC, datetime

import pytest

from app.domain.mapping import to_invoice, to_payment

CREATED = 1756728000  # 2025-09-01T12:00:00Z


def _pi(**overrides: object) -> dict[str, object]:
    """A succeeded PaymentIntent as Stripe returns it with latest_charge and customer expanded."""
    base: dict[str, object] = {
        "id": "pi_1",
        "amount": 4500,
        "status": "succeeded",
        "created": CREATED,
        "description": "Consulting",
        "metadata": {},
        "customer": {"id": "cus_1", "name": "Maya Chen", "email": "maya@example.com"},
        "latest_charge": {"id": "ch_1", "refunded": False, "amount_refunded": 0, "outcome": None},
        "last_payment_error": None,
    }
    base.update(overrides)
    return base


def test_occurred_at_prefers_demo_created_at() -> None:
    """Seeded history carries its intended timestamp in metadata."""
    payment = to_payment(_pi(metadata={"demo_created_at": "2025-08-20T14:30:00+00:00"}))
    assert payment is not None
    assert payment.occurred_at == datetime(2025, 8, 20, 14, 30, tzinfo=UTC)


def test_occurred_at_falls_back_to_created() -> None:
    """Objects created live carry no metadata and use Stripe's own timestamp."""
    payment = to_payment(_pi())
    assert payment is not None
    assert payment.occurred_at == datetime.fromtimestamp(CREATED, tz=UTC)
    assert payment.customer_name == "Maya Chen"
    assert payment.charge_id == "ch_1"
    assert payment.status == "succeeded"


def test_declined_intent_maps_to_failed_with_reason() -> None:
    """A decline is a failed payment whose reason comes from the charge outcome."""
    declined = _pi(
        status="requires_payment_method",
        latest_charge={
            "id": "ch_2",
            "refunded": False,
            "amount_refunded": 0,
            "outcome": {"reason": "insufficient_funds"},
        },
    )
    payment = to_payment(declined)
    assert payment is not None
    assert payment.status == "failed"
    assert payment.failure_reason == "insufficient_funds"


def test_unattempted_intent_is_not_a_payment() -> None:
    """An open invoice's PaymentIntent has no charge yet and must not count as a decline."""
    assert to_payment(_pi(status="requires_payment_method", latest_charge=None)) is None


def test_unexpanded_charge_is_a_programming_error() -> None:
    """A string latest_charge means the caller forgot expand; fail fast rather than mis-map."""
    with pytest.raises(ValueError, match="expand"):
        to_payment(_pi(latest_charge="ch_1"))


def test_refund_states() -> None:
    """Partial and full refunds are distinct statuses so summaries can net them."""
    full = _pi(
        latest_charge={"id": "ch", "refunded": True, "amount_refunded": 4500, "outcome": None}
    )
    part = _pi(
        latest_charge={"id": "ch", "refunded": False, "amount_refunded": 1000, "outcome": None}
    )
    assert to_payment(full).status == "refunded"  # type: ignore[union-attr]
    assert to_payment(part).status == "partially_refunded"  # type: ignore[union-attr]
    assert to_payment(part).amount_refunded_cents == 1000  # type: ignore[union-attr]


def test_invoice_mapping() -> None:
    """Invoices expose what the bot and owner need: remaining balance, due date, hosted URL."""
    invoice = to_invoice(
        {
            "id": "in_1",
            "number": "F-0001",
            "customer": "cus_1",
            "total": 120000,
            "amount_remaining": 120000,
            "status": "open",
            "due_date": CREATED,
            "hosted_invoice_url": "https://invoice.stripe.com/i/x",
            "description": "Q3 retainer",
            "created": CREATED,
            "metadata": {},
        }
    )
    assert invoice.customer_id == "cus_1"
    assert invoice.customer_name is None
    assert invoice.amount_remaining_cents == 120000
    assert invoice.due_at == datetime.fromtimestamp(CREATED, tz=UTC)
