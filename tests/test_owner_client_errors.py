"""Stripe's exceptions become errors that carry a fix the reviewer can apply."""

from datetime import datetime

import pytest
import stripe

from app.stripe_.gateway import CardDeclined, NotFound, StripeGatewayError
from app.stripe_.owner_client import (
    STRIPE_API_VERSION,
    StripeOwnerGateway,
    _plain,
    translate_stripe_errors,
)


def test_authentication_error_names_the_env_variable() -> None:
    """A bad key must tell the reviewer which variable to fix, not say 'unauthorized'."""
    with pytest.raises(StripeGatewayError) as excinfo:
        with translate_stripe_errors():
            raise stripe.AuthenticationError("Invalid API Key provided")
    assert "STRIPE_SECRET_KEY" in excinfo.value.hint


def test_missing_resource_becomes_not_found() -> None:
    """resource_missing is the one InvalidRequestError callers branch on."""
    with pytest.raises(NotFound):
        with translate_stripe_errors():
            raise stripe.InvalidRequestError("No such invoice: in_x", "id", code="resource_missing")


def test_card_error_becomes_card_declined() -> None:
    """A decline while paying an invoice is a user-facing outcome, not a crash."""
    with pytest.raises(CardDeclined):
        with translate_stripe_errors():
            raise stripe.CardError("Your card was declined.", "payment_method", "card_declined")


def test_transport_failure_reads_as_a_sentence_with_the_sdk_text_as_detail() -> None:
    """A network or server failure must not put the SDK's own message on the owner's screen."""
    with pytest.raises(StripeGatewayError) as excinfo:
        with translate_stripe_errors():
            raise stripe.APIConnectionError("Connection reset by peer")
    assert "Connection reset" not in str(excinfo.value)
    assert "Connection reset" in excinfo.value.detail
    assert excinfo.value.hint


def test_client_pins_the_api_version() -> None:
    """The API version is pinned explicitly rather than drifting with the account default."""
    gateway = StripeOwnerGateway("sk_test_placeholder")
    assert gateway.api_version == STRIPE_API_VERSION == "2026-08-26.dahlia"


def test_sdk_objects_convert_to_plain_dicts_for_mapping() -> None:
    """StripeObject.to_dict() recursively converts SDK objects to plain dicts.

    This locks the gateway boundary contract: stripe-python 15's StripeObject
    is not a dict subclass and lacks .get() despite supporting __getitem__
    and __contains__. Domain mapping functions use .get() for optional fields,
    so every SDK object must pass through _plain() before mapping.
    """
    from app.domain.mapping import to_payment

    # Build a realistic PaymentIntent with nested expanded customer and charge
    demo_created_at = "2026-08-15T12:30:00+00:00"
    payload = {
        "id": "pi_1234567890",
        "object": "payment_intent",
        "amount": 5000,
        "status": "succeeded",
        "created": 1692105000,  # 2023-08-15T12:30:00Z (overridden by demo_created_at)
        "metadata": {"demo_created_at": demo_created_at, "created_by": "assistant"},
        "customer": {
            "id": "cus_abc123",
            "object": "customer",
            "name": "Alice",
            "email": "alice@example.com",
            "deleted": False,
        },
        "latest_charge": {
            "id": "ch_1234567890",
            "object": "charge",
            "amount": 5000,
            "refunded": False,
            "amount_refunded": 0,
            "outcome": {"type": "authorized", "reason": None},
        },
        "last_payment_error": None,
        "description": "Test payment",
    }

    # Construct a StripeObject from the dict (simulates SDK response)
    stripe_obj = stripe.StripeObject.construct_from(payload, None)

    # Verify it's NOT a dict (the defect: .get() would fail on raw object)
    assert not isinstance(stripe_obj, dict)

    # Convert to plain dict via _plain()
    plain_dict = _plain(stripe_obj)
    assert isinstance(plain_dict, dict)

    # Verify nested objects are also plain dicts (to_dict() is recursive)
    assert isinstance(plain_dict["customer"], dict)
    assert isinstance(plain_dict["latest_charge"], dict)

    # Mapping function should work with the plain dict
    payment = to_payment(plain_dict)
    assert payment is not None
    assert payment.id == "pi_1234567890"
    assert payment.charge_id == "ch_1234567890"
    assert payment.customer_id == "cus_abc123"
    assert payment.customer_name == "Alice"
    assert payment.amount_cents == 5000
    assert payment.status == "succeeded"

    # Verify demo_created_at is honored (seeded history uses metadata, not created)
    assert payment.occurred_at == datetime.fromisoformat(demo_created_at)
