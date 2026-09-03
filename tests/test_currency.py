"""Resolving an account's settlement currency, and refusing the ones we cannot represent."""

import pytest

from app.domain.currency import USD, Currency, UnsupportedCurrency, resolve
from app.domain.money import format_money


def test_a_two_decimal_currency_resolves_with_its_symbol() -> None:
    """The common case: the reviewer's account settles in dollars."""
    assert resolve("usd") == Currency("usd", "$")


def test_the_code_is_normalised_to_what_stripe_wants_on_writes() -> None:
    """Stripe reports and accepts lowercase; a read must not leak case into a create call."""
    assert resolve("CAD") == Currency("cad", "CA$")
    assert resolve("  eur  ").code == "eur"


def test_an_unlisted_two_decimal_currency_falls_back_to_its_code() -> None:
    """A symbol is a nicety; not having one must never block an account that we can represent."""
    assert resolve("pln") == Currency("pln", "PLN ")


def test_a_zero_decimal_currency_is_refused_by_name() -> None:
    """Every amount in this codebase is integer cents, which JPY has no notion of.

    Refusing beats mishandling: a silent pass renders every figure a hundred
    times too large, and by then the account holds objects that cannot be
    deleted.
    """
    with pytest.raises(UnsupportedCurrency) as caught:
        resolve("jpy")
    assert "JPY" in str(caught.value) and "two decimal places" in str(caught.value)


def test_an_empty_currency_is_refused_rather_than_guessed() -> None:
    """A blank default would otherwise be written to Stripe as an empty currency."""
    with pytest.raises(UnsupportedCurrency):
        resolve("")


def test_usd_is_available_as_a_constant_for_defaults_and_tests() -> None:
    """Callers that predate multi-currency support keep a name for what they assumed."""
    assert USD == resolve("usd")


def test_amounts_are_formatted_in_the_account_currency() -> None:
    """The same cents read differently depending on the account they came from."""
    assert format_money(257_800, resolve("usd")) == "$2,578.00"
    assert format_money(257_800, resolve("cad")) == "CA$2,578.00"
    assert format_money(120_000, resolve("gbp")) == "£1,200.00"


def test_a_negative_amount_signs_before_the_symbol() -> None:
    """Refunds read the way a bank statement prints them."""
    assert format_money(-45_00, resolve("cad")) == "-CA$45.00"


class _FakeAccount:
    """Stands in for the Stripe SDK's Account object, which exposes `to_dict()`."""

    def __init__(self, payload: dict[str, str]) -> None:
        """Hold the payload the SDK would have returned."""
        self._payload = payload

    def to_dict(self) -> dict[str, str]:
        """Mimic the SDK accessor the gateway uses."""
        return self._payload


def test_the_gateway_reads_the_currency_off_the_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The account is asked, never assumed — a wrong guess cannot be undone in Stripe."""
    import stripe

    from app.stripe_.owner_client import StripeOwnerGateway

    monkeypatch.setattr(
        stripe.Account, "retrieve", lambda **_: _FakeAccount({"default_currency": "cad"})
    )
    assert StripeOwnerGateway("sk_test_x").default_currency() == Currency("cad", "CA$")


def test_a_zero_decimal_account_is_refused_at_the_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal has to reach the seed before it creates its first object."""
    import stripe

    from app.stripe_.owner_client import StripeOwnerGateway

    monkeypatch.setattr(
        stripe.Account, "retrieve", lambda **_: _FakeAccount({"default_currency": "jpy"})
    )
    with pytest.raises(UnsupportedCurrency):
        StripeOwnerGateway("sk_test_x").default_currency()
