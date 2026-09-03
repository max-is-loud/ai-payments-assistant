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
    my_balance,
    my_invoices,
    pay_invoice,
)
from app.agent.executor import ActionError
from app.agent.loop import TurnHooks, for_model, run_turn
from app.agent.schema import NoParams
from app.db import escalations
from app.db.engine import session_scope
from app.domain.models import Invoice
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from app.services.escalations import approve_and_notify
from app.stripe_.customer_client import CustomerScopedGateway, NotYourInvoice
from app.telegram.render import reply_for
from tests.fakes.llm_fake import ScriptedLLM
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
    """The planner cannot restate what it never sees: its view of the observation has no figures."""
    with session_scope(engine) as session:
        result = json.dumps(for_model(my_invoices(_acme(session, account), NoParams())))
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


def test_invoice_rows_withhold_the_hosted_page_at_and_above_the_ceiling(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Stripe's hosted invoice page takes payment, so it is a second Pay button.

    Below the ceiling the customer may open it. At or above, the row says the
    owner must approve and carries no URL at all, so neither the planner nor a
    button can hand the customer a way around the escalation.
    """
    account.add_invoice("in_above", "cus_acme", TELEGRAM_PAYMENT_CEILING_CENTS + 4000)
    with session_scope(engine) as session:
        result = my_invoices(_acme(session, account), NoParams())
    rows = {row["invoice_id"]: row for row in result["invoices"]}
    assert rows["in_small"]["view_url"] == "https://invoice.example/in_small"
    assert rows["in_small"]["requires_owner_approval"] is False
    for invoice_id in ("in_big", "in_above"):
        assert rows[invoice_id]["view_url"] is None
        assert rows[invoice_id]["requires_owner_approval"] is True
    assert "invoice.example/in_big" not in json.dumps(result)
    assert "invoice.example/in_above" not in json.dumps(result)


@pytest.mark.parametrize(
    "amount", [TELEGRAM_PAYMENT_CEILING_CENTS, TELEGRAM_PAYMENT_CEILING_CENTS + 4000]
)
def test_repeated_threshold_attempts_reuse_one_escalation_and_never_reach_stripe(
    engine: Engine, account: FakeStripeGateway, amount: int
) -> None:
    """Exactly at the ceiling and above it: every attempt lands on the same escalation row."""
    account.add_invoice("in_x", "cus_acme", amount)
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        first = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_x"))
        assert first.summary is None and first.resolved["escalated"] is True
        for _ in range(2):
            with pytest.raises(ActionError):
                pay_invoice(ctx, PayInvoiceParams(invoice_id="in_x"))
        again = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_x"))
        assert again.resolved["escalation_id"] == first.resolved["escalation_id"]
        pending = escalations.pending(session)
        assert len(pending) == 1
        assert pending[0].invoice_id == "in_x" and pending[0].amount_cents == amount
    assert not [c for c in account.calls if c[0] == "pay_invoice"]


def test_the_hosted_page_is_released_only_once_the_approval_is_durable(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The notifier runs after the approval is committed, never inside its transaction.

    A notifier that reads the escalation through a second session stands in for
    the Telegram send: if it can see `approved`, so can every other process, and
    a crash after the send cannot roll the approval back to pending.
    """
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        proposal = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        esc_id = proposal.resolved["escalation_id"]
    seen: list[tuple[str, str | None]] = []

    def notifier(_telegram_id: int, _text: str, url: str | None) -> bool:
        """Record what a separate connection sees at the moment the link goes out."""
        with session_scope(engine) as other:
            seen.append((escalations.get(other, esc_id).status, url))  # type: ignore[union-attr]
        return True

    with session_scope(engine) as session:
        outcome = approve_and_notify(session, esc_id, gateway=account, notify=notifier, now=NOW)
    assert outcome.notified is True
    assert seen == [("approved", "https://invoice.example/in_big")]


def test_a_pay_tap_after_approval_reuses_the_approved_escalation(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Approval does not make the bot able to charge; it also must not file the request again."""
    with session_scope(engine) as session:
        esc_id = describe_pay_invoice(
            _acme(session, account), PayInvoiceParams(invoice_id="in_big")
        ).resolved["escalation_id"]
    with session_scope(engine) as session:
        approve_and_notify(session, esc_id, gateway=account, notify=lambda *_: True, now=NOW)
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        again = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        assert again.summary is None
        assert again.resolved["escalation_id"] == esc_id
        assert "approved" in again.resolved["message"].lower()
        with pytest.raises(ActionError):
            pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        assert escalations.pending(session) == []
    assert not [c for c in account.calls if c[0] == "pay_invoice"]


def test_the_bots_reply_for_a_threshold_invoice_carries_no_hosted_url(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """End to end through the customer registry and the renderer: text, buttons, callbacks."""
    llm = ScriptedLLM([
        json.dumps({"reasoning": "", "action": "my_balance", "parameters": {}}),
        json.dumps({"reasoning": "", "action": "answer",
                    "parameters": {"text": "You have 2 unpaid invoices."}}),
    ])
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        events = list(run_turn(
            llm=llm, registry=build_customer_registry(), ctx=ctx, system="sys", history=[],
            prompt="what do I owe?",
            hooks=TurnHooks(propose=lambda *a: "act_1", audit=lambda *a: None),
        ))
    reply = reply_for(events)
    buttons = {b.text: (b.url, b.callback_data) for row in reply.buttons for b in row}
    assert buttons["View IN_SMALL"] == ("https://invoice.example/in_small", None)
    assert buttons["Pay IN_SMALL · $1,999.99"] == (None, "pay:in_small")
    assert buttons["IN_BIG · $2,000.00 · needs the owner's approval"] == (None, "pay:in_big")
    assert not any(label.startswith("View IN_BIG") for label in buttons)
    assert reply.text.endswith("You owe <b>$3,999.99</b> across 2 invoices.")
    everything = reply.text + json.dumps(list(buttons.values())) + json.dumps(
        [e.data for e in events], default=str
    )
    assert "invoice.example/in_big" not in everything


def test_an_invoice_payment_is_frozen_at_the_amount_shown_and_fails_when_it_changes(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The confirmation names an amount; approval pays exactly that or asks again."""
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        proposal = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_small"))
        frozen = proposal.params
        assert isinstance(frozen, PayInvoiceParams)
        assert frozen.expected_amount_cents == TELEGRAM_PAYMENT_CEILING_CENTS - 1
        # The balance moves before approval: a credit note, a partial payment elsewhere.
        account.invoices["in_small"] = Invoice(
            **{**account.invoices["in_small"].__dict__, "amount_remaining_cents": 150000}
        )
        ctx.idempotency_key = "act_9"
        with pytest.raises(ActionError, match="changed"):
            pay_invoice(ctx, frozen)
    assert not [c for c in account.calls if c[0] == "pay_invoice"]


def test_the_frozen_amount_is_never_shown_to_the_planner() -> None:
    """The planner cannot be asked to set a figure the server resolves; the catalog omits it."""
    catalog = build_customer_registry().prompt_catalog()
    assert "invoice_id" in catalog
    assert "expected_amount_cents" not in catalog


def test_amounts_travel_to_the_interface_but_never_to_the_planner(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """"What do I owe?" needs a figure; the model that writes the sentence still never sees one.

    The amounts ride under the interface-only `display` key that the loop
    strips from the model's observation. The renderer puts them on buttons
    and in one server-written line, so the customer reads the figure without
    the model ever being able to restate, round, or invent it.
    """
    with session_scope(engine) as session:
        balance = my_balance(_acme(session, account), NoParams())
        listing = my_invoices(_acme(session, account), NoParams())
    assert balance["display"]["invoice_amounts"] == {
        "in_big": "$2,000.00", "in_small": "$1,999.99",
    }
    assert balance["display"]["owed_total"] == "$3,999.99"
    assert listing["display"]["invoice_amounts"] == balance["display"]["invoice_amounts"]
    for result in (balance, listing):
        seen_by_model = json.dumps(for_model(result))
        assert "amount" not in seen_by_model and "$" not in seen_by_model
        assert "display" not in seen_by_model
