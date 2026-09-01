"""Approval executes the stored action — the same parameters, exactly once, with no re-plan."""

import inspect
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine

from app.agent.confirm import (
    AlreadyDecided,
    ConfirmationError,
    UnknownAction,
    UnregisteredAction,
    execute_pending,
)
from app.agent.schema import ActionSpec, Proposal, Registry
from app.db import audit as audit_repo
from app.db import pending_actions
from app.db.engine import session_scope
from app.stripe_.gateway import NotFound
from tests.fakes.stripe_fake import FakeStripeGateway


@dataclass
class Ctx:
    """Minimal handler context honouring the idempotency_key contract."""

    gateway: FakeStripeGateway
    idempotency_key: str | None = None


class RefundParams(BaseModel):
    """Refund parameters."""

    payment_id: str
    amount_cents: int | None = None


def _refund(ctx: Ctx, params: RefundParams) -> dict[str, Any]:
    """Refund through the gateway with the injected idempotency key."""
    refund = ctx.gateway.refund(
        params.payment_id, params.amount_cents, idempotency_key=ctx.idempotency_key or ""
    )
    return {"refund_id": refund.id, "amount_cents": refund.amount_cents}


REGISTRY = Registry([
    ActionSpec("refund", "Refund", RefundParams, _refund, mutation=True,
               describe=lambda ctx, p: Proposal(summary="Refund")),
])


def _stored_refund(engine: Engine, actor: str = "owner") -> str:
    """Store a pending refund of $45.00 on pi_1 and return its action_id."""
    with session_scope(engine) as session:
        row = pending_actions.create(
            session, conversation_id="c1", channel="web", actor=actor, action="refund",
            parameters={"payment_id": "pi_1", "amount_cents": 4500}, summary="Refund $45.00",
            prompt="refund Maya's last payment",
        )
        return row.id


def test_executes_the_stored_parameters_once(engine: Engine) -> None:
    """The gateway receives exactly what was approved; a second approval is refused."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_payment("pi_1", "cus_maya", 9000)
    action_id = _stored_refund(engine)
    with session_scope(engine) as session:
        execution = execute_pending(
            session=session,
            action_id=action_id,
            registry=REGISTRY,
            ctx=Ctx(fake),
            expected_actor="owner",
        )
    assert execution.result == {"refund_id": "re_1", "amount_cents": 4500}
    refund_calls = [c for c in fake.calls if c[0] == "refund"]
    assert refund_calls == [
        (
            "refund",
            {"payment_id": "pi_1", "amount_cents": 4500, "idempotency_key": action_id},
        )
    ]
    with session_scope(engine) as session:
        audit_entries = audit_repo.recent(session)
        assert len(audit_entries) == 1
        assert audit_entries[0].mutation is True
    with session_scope(engine) as session:
        with pytest.raises(AlreadyDecided):
            execute_pending(
                session=session,
                action_id=action_id,
                registry=REGISTRY,
                ctx=Ctx(fake),
                expected_actor="owner",
            )
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1


def test_execute_pending_cannot_consult_a_model() -> None:
    """Structural proof of 'never a freshly planned action': there is no way to pass an LLM."""
    assert "llm" not in inspect.signature(execute_pending).parameters


def test_wrong_actor_or_unknown_id_is_indistinguishable(engine: Engine) -> None:
    """Another actor's action_id is treated as nonexistent so ids cannot be probed."""
    action_id = _stored_refund(engine, actor="telegram:1")
    with session_scope(engine) as session:
        with pytest.raises(UnknownAction):
            execute_pending(
                session=session,
                action_id=action_id,
                registry=REGISTRY,
                ctx=Ctx(FakeStripeGateway()),
                expected_actor="owner",
            )
        with pytest.raises(UnknownAction):
            execute_pending(
                session=session,
                action_id="act_nope",
                registry=REGISTRY,
                ctx=Ctx(FakeStripeGateway()),
                expected_actor="owner",
            )


def test_handler_failure_marks_the_action_failed(engine: Engine) -> None:
    """A Stripe error after claiming must not leave the action re-approvable."""
    action_id = _stored_refund(engine)
    with pytest.raises(NotFound):
        with session_scope(engine) as session:
            execute_pending(
                session=session,
                action_id=action_id,
                registry=REGISTRY,
                ctx=Ctx(FakeStripeGateway()),
                expected_actor="owner",
            )
    with session_scope(engine) as session:
        assert pending_actions.get(session, action_id).status == "failed"  # type: ignore[union-attr]


def test_unregistered_action_is_marked_failed_not_reapprovable(
    engine: Engine,
) -> None:
    """Unregistered action is marked failed durably; a retry raises AlreadyDecided."""
    action_id = _stored_refund(engine, actor="owner")
    registry_missing = Registry([])
    with session_scope(engine) as session:
        with pytest.raises(UnregisteredAction) as exc_info:
            execute_pending(
                session=session,
                action_id=action_id,
                registry=registry_missing,
                ctx=Ctx(FakeStripeGateway()),
                expected_actor="owner",
            )
        assert exc_info.value.code == "unregistered_action"
    with session_scope(engine) as session:
        action = pending_actions.get(session, action_id)
        assert action is not None
        assert action.status == "failed"
    with session_scope(engine) as session:
        with pytest.raises(AlreadyDecided):
            execute_pending(
                session=session,
                action_id=action_id,
                registry=registry_missing,
                ctx=Ctx(FakeStripeGateway()),
                expected_actor="owner",
            )


def test_invalid_stored_parameters_are_marked_failed(engine: Engine) -> None:
    """Invalid parameters (e.g., type mismatch) mark action failed durably."""
    with session_scope(engine) as session:
        row = pending_actions.create(
            session,
            conversation_id="c1",
            channel="web",
            actor="owner",
            action="refund",
            parameters={"payment_id": 123},
            summary="Invalid refund",
            prompt="test",
        )
        action_id = row.id
    with session_scope(engine) as session:
        with pytest.raises(ConfirmationError) as exc_info:
            execute_pending(
                session=session,
                action_id=action_id,
                registry=REGISTRY,
                ctx=Ctx(FakeStripeGateway()),
                expected_actor="owner",
            )
        assert exc_info.value.code == "invalid_stored_action"
    with session_scope(engine) as session:
        action = pending_actions.get(session, action_id)
        assert action is not None
        assert action.status == "failed"
