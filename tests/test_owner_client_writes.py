"""The assistant's own writes name the account's currency, the same as the seed's do.

An invoice or price created in the wrong currency is the same permanent
mistake whether the seed script or the chat box made it. These tests swap a
recording client under the real gateway and pin every create payload.
"""

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
import stripe

from app.domain.currency import Currency
from app.stripe_.owner_client import StripeOwnerGateway


class _Obj:
    """The slice of a Stripe SDK object the gateway reads: attributes plus `to_dict()`."""

    def __init__(self, **fields: Any) -> None:
        """Expose every field as an attribute and keep the dict for `to_dict`."""
        self._fields = fields
        self.__dict__.update(fields)

    def to_dict(self) -> dict[str, Any]:
        """What `_plain` hands to the domain mapping."""
        return self._fields


class _RecordingClient:
    """Records the payload of every create call and answers with just enough object."""

    def __init__(self) -> None:
        """Wire the services `create_invoice` and `create_payment_link` touch."""
        self.calls: list[tuple[str, dict[str, Any]]] = []
        finalized = _Obj(
            id="in_1", customer="cus_1", total=25_000, amount_remaining=25_000,
            status="open", created=1_700_000_000,
        )
        self.v1 = SimpleNamespace(
            invoices=SimpleNamespace(
                create=self._record("invoice", _Obj(id="in_1")),
                finalize_invoice=lambda *_a, **_k: finalized,
            ),
            invoice_items=SimpleNamespace(create=self._record("invoice_item", _Obj(id="ii_1"))),
            prices=SimpleNamespace(create=self._record("price", _Obj(id="price_1"))),
            payment_links=SimpleNamespace(
                create=self._record("link", _Obj(id="plink_1", url="https://buy.stripe.test/x"))
            ),
        )

    def _record(self, label: str, result: _Obj) -> Any:
        """Build a create() stand-in that appends its payload under `label`."""

        def call(params: dict[str, Any], options: dict[str, str] | None = None) -> _Obj:
            """Record and return the canned object."""
            self.calls.append((label, params))
            return result

        return call

    def currency_of(self, label: str) -> set[str | None]:
        """Every distinct currency sent on calls of one kind."""
        return {params.get("currency") for name, params in self.calls if name == label}


@pytest.fixture
def cad_gateway(monkeypatch: pytest.MonkeyPatch) -> tuple[StripeOwnerGateway, _RecordingClient]:
    """A gateway over a Canadian account, with Stripe replaced by a recorder."""
    monkeypatch.setattr(
        stripe.Account, "retrieve",
        lambda **_: _Obj(default_currency="cad"),
    )
    gateway = StripeOwnerGateway("sk_test_x")
    client = _RecordingClient()
    gateway._client = client  # type: ignore[assignment]
    return gateway, client


def test_an_assistant_created_invoice_and_its_item_use_the_account_currency(
    cad_gateway: tuple[StripeOwnerGateway, _RecordingClient],
) -> None:
    """The chat-box path to the exact crash the seed used to hit."""
    gateway, client = cad_gateway
    gateway.create_invoice(
        customer_id="cus_1", amount_cents=25_000, description="Support plan",
        due_date=date(2026, 9, 12), idempotency_key="act_1",
    )
    assert client.currency_of("invoice") == {"cad"}
    assert client.currency_of("invoice_item") == {"cad"}


def test_a_payment_link_price_uses_the_account_currency(
    cad_gateway: tuple[StripeOwnerGateway, _RecordingClient],
) -> None:
    """A USD price on a CAD account would not crash — it would quietly charge the wrong money."""
    gateway, client = cad_gateway
    url = gateway.create_payment_link(
        amount_cents=240_000, description="Licence", idempotency_key="act_2"
    )
    assert url == "https://buy.stripe.test/x"
    assert client.currency_of("price") == {"cad"}


def test_the_account_is_asked_once_per_process(
    cad_gateway: tuple[StripeOwnerGateway, _RecordingClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every write needs the currency; none of them should cost a round trip to get it."""
    gateway, _ = cad_gateway
    assert gateway.default_currency() == Currency("cad", "CA$")
    monkeypatch.setattr(
        stripe.Account, "retrieve",
        lambda **_: (_ for _ in ()).throw(AssertionError("asked the account twice")),
    )
    assert gateway.default_currency() == Currency("cad", "CA$")
