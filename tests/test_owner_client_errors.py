"""Stripe's exceptions become errors that carry a fix the reviewer can apply."""

import pytest
import stripe

from app.stripe_.gateway import CardDeclined, NotFound, StripeGatewayError
from app.stripe_.owner_client import STRIPE_API_VERSION, StripeOwnerGateway, translate_stripe_errors


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


def test_client_pins_the_api_version() -> None:
    """The API version is pinned explicitly rather than drifting with the account default."""
    gateway = StripeOwnerGateway("sk_test_placeholder")
    assert gateway.api_version == STRIPE_API_VERSION == "2026-08-26.dahlia"
