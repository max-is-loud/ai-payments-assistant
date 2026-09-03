"""Every object the seed creates names the account's currency, not a hardcoded one.

Stripe locks a customer to a currency on its first invoice and never releases
it, and payment intents cannot be deleted, so a seed that assumes USD against
a Canadian sandbox leaves permanent wreckage. These tests pin the payloads.
"""

from datetime import date
from types import SimpleNamespace
from typing import Any

from app.domain.currency import resolve
from seed.dataset import build_dataset
from seed.writer import create_invoices, create_payments


class _Created:
    """The bare `.id` the writer reads off a create response."""

    def __init__(self, identifier: str) -> None:
        """Hold the id Stripe would have assigned."""
        self.id = identifier


class _RecordingClient:
    """A Stripe client stand-in that records the payload of every create call."""

    def __init__(self) -> None:
        """Wire the handful of services the writer touches."""
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.v1 = SimpleNamespace(
            invoices=SimpleNamespace(
                create=self._record("invoice", _Created("in_1")),
                finalize_invoice=lambda *_a, **_k: None,
                pay=lambda *_a, **_k: None,
            ),
            invoice_items=SimpleNamespace(create=self._record("invoice_item", _Created("ii_1"))),
            payment_intents=SimpleNamespace(
                create=self._record("payment_intent", _Created("pi_1"))
            ),
        )

    def _record(self, label: str, result: _Created) -> Any:
        """Build a create() stand-in that appends its payload under `label`."""

        def call(params: dict[str, Any], options: dict[str, str] | None = None) -> _Created:
            """Record the payload and hand back a created object."""
            self.calls.append((label, params))
            return result

        return call

    def currencies(self, label: str) -> set[str | None]:
        """Every distinct currency sent on calls of one kind."""
        return {params.get("currency") for name, params in self.calls if name == label}


def _dataset() -> Any:
    """A dataset anchored to a fixed day, so the test does not drift with the calendar."""
    return build_dataset(date(2026, 9, 2))


def _ids(dataset: Any) -> dict[str, str]:
    """Map every customer key to a stand-in Stripe id."""
    return {c.key: f"cus_{i}" for i, c in enumerate(dataset.customers)}


def test_invoices_and_their_items_agree_on_the_account_currency() -> None:
    """The exact failure seen against a Canadian sandbox: a usd item on a cad invoice."""
    dataset, client = _dataset(), _RecordingClient()
    create_invoices(client, dataset, _ids(dataset), resolve("cad"), "run_1", lambda _line: None)
    assert client.currencies("invoice") == {"cad"}
    assert client.currencies("invoice_item") == {"cad"}


def test_payments_carry_the_account_currency_too() -> None:
    """A payment intent in the wrong currency cannot be deleted afterwards."""
    dataset, client = _dataset(), _RecordingClient()
    create_payments(
        client, dataset.payments, _ids(dataset), resolve("eur"), "run_1", lambda _line: None
    )
    assert client.currencies("payment_intent") == {"eur"}


def test_a_usd_account_still_seeds_in_usd() -> None:
    """The common case has to be untouched by making currency a parameter."""
    dataset, client = _dataset(), _RecordingClient()
    create_invoices(client, dataset, _ids(dataset), resolve("usd"), "run_1", lambda _line: None)
    assert client.currencies("invoice") == {"usd"}
