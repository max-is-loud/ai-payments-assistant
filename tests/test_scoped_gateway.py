"""Part 2's whole point: a bound customer cannot reach anyone else's data."""

import inspect

import pytest

from app.stripe_.customer_client import CustomerScopedGateway, NotYourInvoice
from tests.fakes.stripe_fake import FakeStripeGateway


def _two_customers() -> FakeStripeGateway:
    """Acme and Maya, each with one open invoice."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_invoice("in_acme", "cus_acme", 120000)
    fake.add_invoice("in_maya", "cus_maya", 18000)
    return fake


def test_scoped_gateway_lists_only_the_bound_customers_invoices() -> None:
    """Every list call carries the bound id; the other customer's invoice never appears."""
    scoped = CustomerScopedGateway(_two_customers(), "cus_acme")
    assert [i.id for i in scoped.my_invoices()] == ["in_acme"]
    assert scoped.my_customer().name == "Acme Corp"


def test_scoped_gateway_refuses_another_customers_invoice_before_any_payment_call() -> None:
    """Ownership is checked first, so a guessed invoice id cannot be paid or even read."""
    fake = _two_customers()
    scoped = CustomerScopedGateway(fake, "cus_acme")
    with pytest.raises(NotYourInvoice):
        scoped.my_invoice("in_maya")
    with pytest.raises(NotYourInvoice):
        scoped.pay_my_invoice("in_maya", idempotency_key="k")
    assert not [c for c in fake.calls if c[0] == "pay_invoice"]


def test_scoped_gateway_exposes_no_customer_id_parameter() -> None:
    """Structural check: no public method can be steered towards another customer."""
    for name, member in inspect.getmembers(CustomerScopedGateway, inspect.isfunction):
        if name.startswith("_"):
            continue
        assert "customer_id" not in inspect.signature(member).parameters, name


def test_scoped_gateway_raises_not_your_invoice_for_missing_invoice_ids() -> None:
    """Unknown invoice ids raise NotYourInvoice, same as foreign ones."""
    fake = _two_customers()
    scoped = CustomerScopedGateway(fake, "cus_acme")
    with pytest.raises(NotYourInvoice, match="No such invoice on your account."):
        scoped.my_invoice("in_ghost")
    with pytest.raises(NotYourInvoice, match="No such invoice on your account."):
        scoped.pay_my_invoice("in_ghost", idempotency_key="k")
    assert not [c for c in fake.calls if c[0] == "pay_invoice"]
