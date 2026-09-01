"""Map Stripe API objects to domain records.

This module is the single place that knows Stripe's field names, and the
single reader of `metadata.demo_created_at`. Stripe SDK objects are dict
subclasses, so every function takes a Mapping and tests pass plain dicts.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.domain.models import Customer, Invoice, Payment, PaymentStatus, Refund


def _occurred_at(obj: Mapping[str, Any]) -> datetime:
    """Business timestamp of an object.

    Seeded history cannot carry a past `created` (Stripe assigns it), so the
    seed script records the intended moment in metadata. Deleting the first
    branch makes this production behaviour; nothing else reads the field.
    """
    demo = (obj.get("metadata") or {}).get("demo_created_at")
    if demo:
        parsed = datetime.fromisoformat(demo)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.fromtimestamp(obj["created"], tz=UTC)


def _customer_ref(value: Any) -> tuple[str | None, str | None]:
    """Split a `customer` field into (id, name) whether or not it was expanded."""
    if value is None:
        return None, None
    if isinstance(value, str):
        return value, None
    if value.get("deleted"):
        return value.get("id"), None
    return value.get("id"), value.get("name")


def to_payment(obj: Mapping[str, Any]) -> Payment | None:
    """Map a PaymentIntent (with `latest_charge` and `customer` expanded).

    Returns None for an intent that was never attempted — an open invoice's
    intent, for instance — because it is neither a payment nor a decline.

    Raises:
        ValueError: `latest_charge` is an id string, meaning the caller forgot
            `expand=["data.latest_charge"]`; mapping blind would hide declines.
    """
    charge = obj.get("latest_charge")
    if charge is None:
        return None
    if isinstance(charge, str):
        raise ValueError("PaymentIntent.latest_charge must be expanded before mapping")
    customer_id, customer_name = _customer_ref(obj.get("customer"))
    status: PaymentStatus
    failure_reason: str | None = None
    if obj["status"] == "succeeded":
        if charge.get("refunded"):
            status = "refunded"
        elif charge.get("amount_refunded"):
            status = "partially_refunded"
        else:
            status = "succeeded"
    else:
        status = "failed"
        outcome = charge.get("outcome") or {}
        error = obj.get("last_payment_error") or {}
        failure_reason = (
            outcome.get("reason") or error.get("decline_code") or charge.get("failure_code")
        )
    return Payment(
        id=obj["id"],
        charge_id=charge["id"],
        customer_id=customer_id,
        customer_name=customer_name,
        amount_cents=obj["amount"],
        amount_refunded_cents=charge.get("amount_refunded") or 0,
        status=status,
        failure_reason=failure_reason,
        description=obj.get("description"),
        occurred_at=_occurred_at(obj),
    )


def to_invoice(obj: Mapping[str, Any]) -> Invoice:
    """Map an Invoice; `customer` may be an id or an expanded object."""
    customer_id, customer_name = _customer_ref(obj.get("customer"))
    due = obj.get("due_date")
    return Invoice(
        id=obj["id"],
        number=obj.get("number"),
        customer_id=customer_id or "",
        customer_name=customer_name,
        total_cents=obj.get("total") or 0,
        amount_remaining_cents=obj.get("amount_remaining") or 0,
        status=obj.get("status") or "draft",
        due_at=datetime.fromtimestamp(due, tz=UTC) if due else None,
        hosted_url=obj.get("hosted_invoice_url"),
        description=obj.get("description"),
        occurred_at=_occurred_at(obj),
    )


def to_customer(obj: Mapping[str, Any]) -> Customer:
    """Map a Customer. Deleted customers keep their id and lose their name."""
    return Customer(id=obj["id"], name=obj.get("name") or "(unnamed)", email=obj.get("email"))


def to_refund(obj: Mapping[str, Any]) -> Refund:
    """Map a Refund created against a PaymentIntent."""
    return Refund(
        id=obj["id"],
        payment_id=obj.get("payment_intent") or "",
        amount_cents=obj["amount"],
        status=obj.get("status") or "pending",
    )
