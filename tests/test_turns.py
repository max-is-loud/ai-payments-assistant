"""Sync glue between Telegram updates and the agent, over fakes."""

import json

from sqlalchemy import Engine

from app.settings import Settings
from app.telegram.turns import (
    BotDeps,
    bind_token,
    confirm_action,
    customer_turn,
    propose_payment,
    resolve_customer,
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
