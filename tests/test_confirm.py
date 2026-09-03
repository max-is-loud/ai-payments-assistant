"""Approval executes the stored action — the same parameters, exactly once, with no re-plan.

The second half of this file is the lifecycle: the claim, the Stripe call, and
the record are three short transactions, so a slow provider never holds the
SQLite writer lock, a dropped stream cannot roll a finished execution back to
pending, and an execution the process died in the middle of can be finished
later with the same idempotency key.
"""

import inspect
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.agent.confirm import (
    AlreadyDecided,
    ConfirmationError,
    UnknownAction,
    UnregisteredAction,
    execute_pending,
)
from app.agent.schema import ActionSpec, Proposal, Registry
from app.db import audit as audit_repo
from app.db import conversations, pending_actions
from app.db.engine import session_scope
from app.stripe_.gateway import NotFound
from tests.fakes.stripe_fake import FakeStripeGateway


@dataclass
class Ctx:
    """Minimal handler context honouring the idempotency_key contract."""

    gateway: FakeStripeGateway
    idempotency_key: str | None = None
    recovering: bool = False


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
    with session_scope(engine) as session:
        stored_key = pending_actions.get(session, action_id).idempotency_key  # type: ignore[union-attr]
    assert stored_key, "the execution key is persisted with the claim"
    refund_calls = [c for c in fake.calls if c[0] == "refund"]
    assert refund_calls == [
        (
            "refund",
            {"payment_id": "pi_1", "amount_cents": 4500, "idempotency_key": stored_key},
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


class _BlockingGateway(FakeStripeGateway):
    """A gateway whose refund waits until the test lets it through, like a slow Stripe."""

    def __init__(self) -> None:
        """Two events: the handler has entered Stripe; the test allows it to return."""
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Any:
        """Signal entry, then wait for the test before answering."""
        self.entered.set()
        assert self.release.wait(10), "the test never released the gateway"
        return super().refund(payment_id, amount_cents, idempotency_key=idempotency_key)


def _account(fake: FakeStripeGateway) -> FakeStripeGateway:
    """Maya paid $90 on pi_1."""
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_payment("pi_1", "cus_maya", 9000)
    return fake


def _approve(
    engine: Engine, fake: FakeStripeGateway, action_id: str, out: dict[str, Any], label: str
) -> None:
    """Run one approval and store its execution or its refusal under `label`."""
    try:
        with session_scope(engine) as session:
            out[label] = execute_pending(
                session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake),
                expected_actor="owner",
            )
    except ConfirmationError as exc:
        out[label] = exc


def test_a_slow_stripe_call_holds_no_writer_lock(engine: Engine) -> None:
    """An unrelated write from another connection lands while Stripe is still working.

    The claim is committed before the handler runs, so the only thing open
    during the Stripe call is the handler's own read. The bot's writes, the
    owner's next turn, and the audit of a read must not queue behind it.
    """
    fake = _account(_BlockingGateway())
    action_id = _stored_refund(engine)
    out: dict[str, Any] = {}
    worker = threading.Thread(
        target=_approve, args=(engine, fake, action_id, out, "it"), daemon=True
    )
    worker.start()
    assert fake.entered.wait(5)
    started = time.monotonic()
    try:
        with session_scope(engine) as session:
            conversations.append(session, "other", "user", "unrelated")
    finally:
        elapsed = time.monotonic() - started
        fake.release.set()
        worker.join(10)
    assert elapsed < 1.0, f"an unrelated write waited {elapsed:.1f}s on the confirmation"
    assert out["it"].result["amount_cents"] == 4500


def test_a_rollback_after_execution_cannot_return_the_action_to_pending(engine: Engine) -> None:
    """What a dropped SSE stream does to the route's session must not undo the claim.

    Closing a generator mid-stream ends the enclosing session without a
    commit: `GeneratorExit` is not an `Exception`, so the scope's rollback
    branch never runs, and `close()` discards the open transaction all the
    same. Everything the execution needs durable is therefore committed
    before `execute_pending` returns; the caller's transaction holds nothing.
    """
    fake = _account(FakeStripeGateway())
    action_id = _stored_refund(engine)
    session = Session(engine)
    try:
        execute_pending(
            session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake),
            expected_actor="owner",
        )
    finally:
        session.close()  # no commit: whatever the caller still held is thrown away
    with session_scope(engine) as check:
        row = pending_actions.get(check, action_id)
        assert row is not None and row.status == "executed"
        assert json.loads(row.result_json or "{}")["amount_cents"] == 4500
        assert len(audit_repo.recent(check)) == 1
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1


def test_concurrent_approvals_produce_one_stripe_operation(engine: Engine) -> None:
    """A second approval that arrives while the first is inside Stripe is refused at once."""
    fake = _account(_BlockingGateway())
    action_id = _stored_refund(engine)
    out: dict[str, Any] = {}
    first = threading.Thread(
        target=_approve, args=(engine, fake, action_id, out, "first"), daemon=True
    )
    first.start()
    assert fake.entered.wait(5)
    started = time.monotonic()
    try:
        _approve(engine, fake, action_id, out, "second")
    finally:
        waited = time.monotonic() - started
        fake.release.set()
        first.join(10)
    assert waited < 1.0, f"the second approval waited {waited:.1f}s instead of being refused"
    assert isinstance(out["second"], ConfirmationError) and out["second"].code == "in_progress"
    assert out["first"].result["amount_cents"] == 4500
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1


def test_a_crash_between_stripe_and_finalisation_is_recovered_without_a_second_operation(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process dies after Stripe answered and before the row was finalised.

    `SystemExit` stands in for the kill: nothing in the lifecycle catches it,
    so the row stays `executing` with its key. Recovery re-runs the handler
    with that key, and the gateway, like Stripe, replays the original result
    instead of refunding again.
    """
    from app.agent.confirm import recover_executing

    fake = _account(FakeStripeGateway())
    action_id = _stored_refund(engine)

    def die(*_args: Any, **_kwargs: Any) -> None:
        """The kill lands just after Stripe returned."""
        raise SystemExit("killed between Stripe and finalisation")

    monkeypatch.setattr(pending_actions, "finish", die)
    with pytest.raises(SystemExit):
        with session_scope(engine) as session:
            execute_pending(
                session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake),
                expected_actor="owner",
            )
    monkeypatch.undo()
    with session_scope(engine) as session:
        row = pending_actions.get(session, action_id)
        assert row is not None and row.status == "executing" and row.idempotency_key
        stored_key = row.idempotency_key
    with session_scope(engine) as session:
        recovered = recover_executing(
            session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake)
        )
    assert recovered.result == {"refund_id": "re_1", "amount_cents": 4500}
    expected = (
        "refund", {"payment_id": "pi_1", "amount_cents": 4500, "idempotency_key": stored_key}
    )
    assert [c for c in fake.calls if c[0] == "refund"] == [expected]
    assert fake.replays == [expected]
    with session_scope(engine) as session:
        assert pending_actions.get(session, action_id).status == "executed"  # type: ignore[union-attr]
        assert len(audit_repo.recent(session)) == 1


def _age_claim(engine: Engine, action_id: str, age: Any) -> None:
    """Backdate the claim, as a row left behind long ago would be."""
    from sqlalchemy import update

    from app.db.clock import utcnow
    from app.db.models import PendingAction

    with session_scope(engine) as session:
        session.execute(
            update(PendingAction)
            .where(PendingAction.id == action_id)
            .values(claimed_at=utcnow() - age)
        )


def test_an_interrupted_execution_older_than_the_recovery_window_is_parked_for_review(
    engine: Engine,
) -> None:
    """Stripe honours an idempotency key for 24 hours; after that a replay could be a new operation.

    A row claimed before the window is not re-driven. It is parked as
    `needs_review` with its key recorded for a manual check against Stripe,
    the audit log says so, and no approval can ever run it again.
    """
    from datetime import timedelta

    from app.agent.confirm import NeedsReview, recover_executing
    from app.domain.policy import EXECUTION_RECOVERY_WINDOW

    fake = _account(FakeStripeGateway())
    action_id = _stored_refund(engine)
    with session_scope(engine) as session:
        assert pending_actions.claim(session, action_id, idempotency_key="exec_old")
    _age_claim(engine, action_id, EXECUTION_RECOVERY_WINDOW + timedelta(minutes=1))
    with session_scope(engine) as session:
        with pytest.raises(NeedsReview) as caught:
            recover_executing(
                session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake)
            )
    assert caught.value.code == "needs_review" and "exec_old" in str(caught.value)
    assert not [c for c in fake.calls if c[0] == "refund"]
    with session_scope(engine) as session:
        row = pending_actions.get(session, action_id)
        assert row is not None and row.status == "needs_review"
        assert json.loads(row.result_json or "{}")["idempotency_key"] == "exec_old"
        entries = audit_repo.recent(session)
        assert len(entries) == 1 and "exec_old" in entries[0].result_json
    with session_scope(engine) as session:
        with pytest.raises(AlreadyDecided, match="manual"):
            execute_pending(
                session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake),
                expected_actor="owner",
            )


def test_an_interrupted_execution_inside_the_window_is_still_recovered(engine: Engine) -> None:
    """Just inside the window the stored key is replayed as before."""
    from datetime import timedelta

    from app.agent.confirm import recover_executing
    from app.domain.policy import EXECUTION_RECOVERY_WINDOW

    fake = _account(FakeStripeGateway())
    action_id = _stored_refund(engine)
    with session_scope(engine) as session:
        assert pending_actions.claim(session, action_id, idempotency_key="exec_recent")
    _age_claim(engine, action_id, EXECUTION_RECOVERY_WINDOW - timedelta(minutes=1))
    with session_scope(engine) as session:
        recovered = recover_executing(
            session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake)
        )
    assert recovered.result["amount_cents"] == 4500
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1
