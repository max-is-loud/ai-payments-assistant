"""Unknown parameters are a planner mistake to correct, never something to ignore.

A misspelt field on a lenient model does not fail; it disappears. `amount`
instead of `amount_cents` turned a partial refund into a full one, and
`statuz` instead of `status` turned a filtered query into an unfiltered one.
Every parameter model now forbids unknown keys, and the loop treats the
rejection as a recoverable retry.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine

from app.actions.context import CustomerContext
from app.actions.customer import build_customer_registry
from app.actions.owner_registry import build_owner_registry
from app.agent.executor import ActionError, resolve, validate_params
from app.agent.loop import TurnHooks, run_turn
from app.agent.schema import TERMINAL_ACTIONS, ActionCall
from app.db.engine import session_scope
from app.stripe_.customer_client import CustomerScopedGateway
from tests.fakes.llm_fake import ScriptedLLM
from tests.fakes.stripe_fake import FakeStripeGateway

OWNER = build_owner_registry()
CUSTOMER = build_customer_registry()


def _step(action: str, **parameters: Any) -> str:
    """A planner step as the model would emit it."""
    return json.dumps({"reasoning": "r", "action": action, "parameters": parameters})


def test_a_misspelt_refund_amount_is_rejected_not_turned_into_a_full_refund() -> None:
    """`amount` is not `amount_cents`; silently dropping it would refund the whole payment."""
    with pytest.raises(ActionError, match="amount"):
        resolve(OWNER, ActionCall(action="refund_payment", parameters={
            "payment_id": "pi_1", "amount": 5000,
        }))


def test_a_misspelt_query_filter_is_rejected_not_turned_into_an_unfiltered_query() -> None:
    """`statuz` is not `status`; dropping it would list every payment as if none had failed."""
    with pytest.raises(ActionError, match="statuz"):
        resolve(OWNER, ActionCall(action="query_payments", parameters={"statuz": "failed"}))


@pytest.mark.parametrize(
    ("registry", "action", "parameters"),
    [
        (OWNER, "refund_payment", {"payment_id": "pi_1", "reason": "duplicate"}),
        (OWNER, "create_invoice", {
            "customer_id": "cus_1", "amount_cents": 100, "description": "x",
            "due_date": "2027-01-01", "send": True,
        }),
        (OWNER, "list_invoices", {"customer": "cus_1"}),
        (OWNER, "find_customer", {"name": "maya"}),
        (OWNER, "summarize_day", {"date": "2026-09-01"}),
        (CUSTOMER, "my_balance", {"customer_id": "cus_other"}),
        (CUSTOMER, "pay_invoice", {"invoice_id": "in_1", "amount_cents": 1}),
    ],
)
def test_unknown_fields_are_rejected_on_every_action(
    registry: Any, action: str, parameters: dict[str, Any]
) -> None:
    """Reads, mutations, and no-parameter actions alike name the stray field in the error."""
    stray = next(iter(set(parameters) - set(registry.get(action).params.model_fields)))
    with pytest.raises(ActionError, match=stray):
        resolve(registry, ActionCall(action=action, parameters=parameters))


def test_unknown_fields_are_rejected_on_answer_and_clarify() -> None:
    """The terminal actions are validated through the same models and forbid extras too."""
    with pytest.raises(Exception, match="tone"):
        validate_params(TERMINAL_ACTIONS["answer"], {"text": "hi", "tone": "warm"})
    with pytest.raises(Exception, match="options"):
        validate_params(TERMINAL_ACTIONS["clarify"], {"question": "which?", "options": []})


def test_null_still_means_omitted_for_known_fields_only() -> None:
    """A `null` on a real optional field is dropped; on an unknown field it is still an error."""
    _spec, params = resolve(OWNER, ActionCall(action="query_payments", parameters={
        "customer_id": None, "limit": None,
    }))
    assert params.customer_id is None and params.limit == 20  # type: ignore[attr-defined]
    with pytest.raises(ActionError, match="statuz"):
        resolve(OWNER, ActionCall(action="query_payments", parameters={"statuz": None}))


def test_a_rejected_step_is_a_retry_and_no_handler_runs_until_the_step_is_corrected(
    engine: Engine,
) -> None:
    """The customer bot: a stray `customer_id` never reaches Stripe; the corrected step does."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_invoice("in_1", "cus_acme", 120000)
    llm = ScriptedLLM([
        _step("my_balance", customer_id="cus_maya"),
        _step("my_balance"),
        _step("answer", text="1 unpaid invoice.", tone="warm"),
        _step("answer", text="1 unpaid invoice."),
    ])
    with session_scope(engine) as session:
        ctx = CustomerContext(
            gateway=CustomerScopedGateway(fake, "cus_acme"), session=session, telegram_id=7,
            customer_name="Acme Corp", now=datetime(2026, 9, 1, tzinfo=UTC),
        )
        events = list(run_turn(
            llm=llm, registry=CUSTOMER, ctx=ctx, system="sys", history=[], prompt="owe?",
            hooks=TurnHooks(propose=lambda *a: "act_1", audit=lambda *a: None),
        ))
    types = [e.type for e in events]
    assert types == [
        "planning", "error",  # stray customer_id: rejected, nothing ran
        "planning", "action", "observation",  # corrected step runs once
        "planning", "error",  # stray tone on answer: rejected
        "planning", "answer",
    ]
    assert events[1].data["code"] == "planner_retry"
    assert "customer_id" in events[1].data["detail"]
    assert events[6].data["code"] == "planner_retry" and "tone" in events[6].data["detail"]
    assert [c[0] for c in fake.calls] == ["list_invoices"]
    assert events[-1].data == {"text": "1 unpaid invoice."}
