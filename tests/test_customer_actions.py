"""The bot's guardrails are Python invariants: the ceiling, the scope, and amount-free replies."""

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine

from app.actions.context import CustomerContext
from app.actions.customer import (
    PayInvoiceParams,
    build_customer_registry,
    describe_pay_invoice,
    my_invoices,
    pay_invoice,
)
from app.agent.executor import ActionError
from app.agent.schema import NoParams
from app.db import escalations
from app.db.engine import session_scope
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from app.stripe_.customer_client import CustomerScopedGateway, NotYourInvoice
from tests.fakes.stripe_fake import FakeStripeGateway

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)


@pytest.fixture
def account() -> FakeStripeGateway:
    """Acme has one invoice exactly at the ceiling and one just under; Maya has one."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_invoice("in_big", "cus_acme", TELEGRAM_PAYMENT_CEILING_CENTS)
    fake.add_invoice("in_small", "cus_acme", TELEGRAM_PAYMENT_CEILING_CENTS - 1)
    fake.add_invoice("in_maya", "cus_maya", 18000)
    return fake


def _acme(engine_session: object, fake: FakeStripeGateway) -> CustomerContext:
    """A context bound to Acme."""
    return CustomerContext(
        gateway=CustomerScopedGateway(fake, "cus_acme"), session=engine_session,  # type: ignore[arg-type]
        telegram_id=7, customer_name="Acme Corp", now=NOW,
    )


def test_ceiling_escalates_before_any_stripe_payment_call(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """At exactly $2,000 the bot files an escalation and never reaches invoices.pay."""
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        proposal = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        assert proposal.summary is None and proposal.resolved["escalated"] is True
        with pytest.raises(ActionError):
            pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        # the second attempt reused the first
        assert len(escalations.pending(session)) == 1
    assert not [c for c in account.calls if c[0] == "pay_invoice"]


def test_under_ceiling_confirms_with_amount_then_pays(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Just under ceiling is payable; amount appears in confirmation only."""
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        proposal = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_small"))
        expected_summary = "Pay invoice IN_SMALL for $1,999.99 with your card on file"
        assert proposal.summary == expected_summary
        ctx.idempotency_key = "act_9"
        result = pay_invoice(ctx, PayInvoiceParams(invoice_id="in_small"))
    assert result["paid"] is True
    expected_call = ("pay_invoice", {"invoice_id": "in_small", "idempotency_key": "act_9"})
    assert account.calls[-1] == expected_call


def test_another_customers_invoice_is_unreachable(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """A guessed invoice id belonging to Maya fails ownership before anything else."""
    with session_scope(engine) as session:
        with pytest.raises(NotYourInvoice):
            pay_invoice(_acme(session, account), PayInvoiceParams(invoice_id="in_maya"))


def test_customer_observations_carry_no_amounts(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The planner cannot restate what it never sees."""
    with session_scope(engine) as session:
        result = json.dumps(my_invoices(_acme(session, account), NoParams()))
    assert "amount" not in result
    assert "total" not in result
    assert str(TELEGRAM_PAYMENT_CEILING_CENTS) not in result
    assert "view_url" in result


def test_customer_registry_has_no_customer_id_anywhere() -> None:
    """Structural: no customer action accepts a customer id, so no prompt can supply one."""
    registry = build_customer_registry()
    assert registry.names() == ["my_balance", "my_invoices", "pay_invoice", "escalate_to_owner"]
    for spec in registry.specs():
        assert "customer_id" not in spec.params.model_fields, spec.name
