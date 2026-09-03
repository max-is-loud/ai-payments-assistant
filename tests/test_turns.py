"""Sync glue between Telegram updates and the agent, over fakes."""

import json

from sqlalchemy import Engine

from app.db import pending_actions
from app.db.engine import session_scope
from app.settings import Settings
from app.telegram.turns import (
    BotDeps,
    bind_token,
    confirm_action,
    customer_turn,
    propose_payment,
    recover_interrupted,
    resolve_customer,
    revoke,
)
from tests.fakes.llm_fake import ScriptedLLM
from tests.fakes.stripe_fake import FakeStripeGateway


def _deps(engine: Engine, llm: ScriptedLLM) -> tuple[BotDeps, FakeStripeGateway]:
    """Acme bound via token 'tok-acme' with one $1,200 invoice."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp", bind_token="tok-acme")
    fake.add_invoice("in_1", "cus_acme", 120000)
    return BotDeps(settings=Settings(_env_file=None), gateway=fake, llm=llm, engine=engine), fake


def test_bind_then_turn_then_pay_via_buttons(engine: Engine) -> None:
    """/start <token> binds; a question runs the customer registry; Pay → Confirm charges once."""
    llm = ScriptedLLM([
        json.dumps({"reasoning": "", "action": "my_balance", "parameters": {}}),
        json.dumps({
            "reasoning": "", "action": "answer", "parameters": {"text": "1 unpaid invoice."},
        }),
    ])
    deps, fake = _deps(engine, llm)
    assert bind_token(deps, 7, "nope") is None
    assert bind_token(deps, 7, "tok-acme") == "Acme Corp"
    binding = resolve_customer(deps, 7)
    assert binding is not None and binding.stripe_customer_id == "cus_acme"
    events = customer_turn(deps, binding, "what do I owe?")
    assert events[-1].data["text"] == "1 unpaid invoice."
    proposal = propose_payment(deps, binding, "in_1")
    assert proposal[-1].type == "confirmation"
    reply = confirm_action(deps, binding, proposal[-1].data["action_id"])
    assert "receipt" in reply.text.lower() or "paid" in reply.text.lower()
    assert len([c for c in fake.calls if c[0] == "pay_invoice"]) == 1
    replay = confirm_action(deps, binding, proposal[-1].data["action_id"]).text.lower()
    assert "expired" in replay or "already" in replay


def test_interrupted_telegram_executions_are_recovered_at_bot_startup(engine: Engine) -> None:
    """A payment the bot process died in the middle of is finished with the same key.

    The customer's binding is looked up by the Telegram id on the row, so the
    handler runs under the same scoped gateway it was approved under, and the
    fake replays the invoice payment instead of charging twice.
    """
    deps, fake = _deps(engine, ScriptedLLM([]))
    bind_token(deps, 7, "tok-acme")
    fake.pay_invoice("in_1", idempotency_key="exec_dead")  # what the dead process did
    with session_scope(engine) as session:
        row = pending_actions.create(
            session, conversation_id="telegram:7", channel="telegram", actor="telegram:7",
            action="pay_invoice", parameters={"invoice_id": "in_1"}, summary="Pay invoice IN_1",
            prompt="(tapped Pay in_1)",
        )
        assert pending_actions.claim(session, row.id, idempotency_key="exec_dead")
        action_id = row.id
    assert recover_interrupted(deps) == [action_id]
    with session_scope(engine) as session:
        row = pending_actions.get(session, action_id)
        assert row is not None and row.status == "executed"
    assert len([c for c in fake.calls if c[0] == "pay_invoice"]) == 1
    assert len(fake.replays) == 1
    assert recover_interrupted(deps) == []


def test_the_pay_button_stores_the_amount_the_customer_confirmed(engine: Engine) -> None:
    """The frozen amount travels with the stored action, not only with the sentence."""
    deps, _fake = _deps(engine, ScriptedLLM([]))
    bind_token(deps, 7, "tok-acme")
    binding = resolve_customer(deps, 7)
    assert binding is not None
    proposal = propose_payment(deps, binding, "in_1")
    with session_scope(engine) as session:
        row = pending_actions.get(session, proposal[-1].data["action_id"])
        assert row is not None
        assert json.loads(row.parameters_json) == {
            "invoice_id": "in_1", "expected_amount_cents": 120000,
        }


def test_a_binding_token_binds_once_and_never_again(engine: Engine) -> None:
    """A token is consumed by its first use; a second account presenting it is refused."""
    deps, fake = _deps(engine, ScriptedLLM([]))
    assert bind_token(deps, 7, "tok-acme") == "Acme Corp"
    assert bind_token(deps, 8, "tok-acme") is None
    assert resolve_customer(deps, 8) is None
    # The same account re-sending its own link is not a new binding, just a confirmation.
    assert bind_token(deps, 7, "tok-acme") == "Acme Corp"


def test_logout_expiry_and_owner_revocation_cannot_be_undone_by_replaying_the_token(
    engine: Engine,
) -> None:
    """Once a binding ends, the token that made it is spent; only a new token binds again."""
    from datetime import timedelta

    from app.db import bindings
    from app.db.clock import utcnow

    deps, _fake = _deps(engine, ScriptedLLM([]))
    assert bind_token(deps, 7, "tok-acme") == "Acme Corp"
    assert revoke(deps, 7) is True
    assert bind_token(deps, 7, "tok-acme") is None
    assert resolve_customer(deps, 7) is None

    # Owner-side revocation and inactivity expiry end the binding the same way.
    with session_scope(engine) as session:
        bindings.bind(
            session, telegram_id=9, customer_id="cus_acme", customer_name="Acme Corp",
            now=utcnow() - timedelta(days=30),
        )
    assert resolve_customer(deps, 9) is None  # expired on first contact
    assert bind_token(deps, 9, "tok-acme") is None
    with session_scope(engine) as session:
        bindings.revoke_for_customer(session, "cus_acme", utcnow())
    assert bind_token(deps, 9, "tok-acme") is None


def test_two_accounts_racing_for_one_token_bind_at_most_one(engine: Engine) -> None:
    """The consumed-token row's primary key is the arbiter; two threads cannot both win."""
    import threading

    deps, _fake = _deps(engine, ScriptedLLM([]))
    outcomes: dict[int, str | None] = {}

    def attempt(telegram_id: int) -> None:
        """Bind from one thread."""
        outcomes[telegram_id] = bind_token(deps, telegram_id, "tok-acme")

    threads = [threading.Thread(target=attempt, args=(tid,)) for tid in (21, 22, 23, 24)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert sorted(v for v in outcomes.values() if v) == ["Acme Corp"]
    bound = [tid for tid in outcomes if resolve_customer(deps, tid) is not None]
    assert len(bound) == 1
