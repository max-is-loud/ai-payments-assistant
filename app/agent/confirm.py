"""Execute a previously proposed mutation.

The stored action is the contract: approval runs exactly the parameters the
user saw, under the registry that produced them. No model is consulted here,
which is why this module cannot import an LLM.

Execution is three short transactions, never one long one:

1. The claim: `pending → executing`, with a freshly minted idempotency key
   stored on the row, committed before anything else happens.
2. The handler: the Stripe call, with no write transaction open.
3. The record: the result and the audit entry, `executing → executed`,
   committed.

So a slow provider never holds the SQLite writer lock that the bot and the
owner's next turn need; a client that drops the stream after step 3 cannot
roll the execution back; and a process that dies between steps 2 and 3
leaves a row that `recover_executing` finishes under the same key, which
Stripe answers with the original result rather than a second operation.
That replay is only safe while Stripe still holds the key, so recovery is
bounded by `EXECUTION_RECOVERY_WINDOW`; an older row is parked for a
manual check instead of being replayed.
"""

import dataclasses
import json
import secrets
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.events import to_jsonable
from app.agent.schema import Registry
from app.db import audit, pending_actions
from app.db.clock import utcnow
from app.db.models import PendingAction
from app.domain.policy import EXECUTION_RECOVERY_WINDOW


class ConfirmationError(Exception):
    """A confirmation could not proceed; `code` is stable for the API envelope."""

    def __init__(self, code: str, message: str) -> None:
        """Store a machine code and a human message."""
        super().__init__(message)
        self.code = code


class UnknownAction(ConfirmationError):
    """No pending action with this id for this actor."""

    def __init__(self) -> None:
        """Same wording for missing and foreign ids so they cannot be told apart."""
        super().__init__("unknown_action", "That confirmation has expired or does not exist.")


class AlreadyDecided(ConfirmationError):
    """The action was already executed, cancelled, failed, or parked for review."""

    def __init__(self, status: str) -> None:
        """Name the status so a double-click shows 'already executed', not an error."""
        if status == "needs_review":
            message = (
                "That action needs a manual check against Stripe before anything else "
                "happens; see the audit log for its idempotency key."
            )
        else:
            message = f"That action was already {status}."
        super().__init__("already_decided", message)


class NeedsReview(ConfirmationError):
    """An interrupted execution too old to finish safely; a person must settle it."""

    def __init__(self, action_id: str, key: str) -> None:
        """Name the key, which is what a person looks up in Stripe's request log."""
        super().__init__(
            "needs_review",
            f"Execution {action_id} was interrupted too long ago to finish safely and needs a "
            f"manual check: look up idempotency key {key} in Stripe's request log and settle "
            "it by hand.",
        )


class InProgress(ConfirmationError):
    """Another approval claimed the action and has not finished with Stripe yet."""

    def __init__(self) -> None:
        """A second click while the first is inside Stripe is refused, not queued."""
        super().__init__("in_progress", "That action is still being executed.")


class UnregisteredAction(ConfirmationError):
    """The action name is no longer in the registry."""

    def __init__(self, action: str) -> None:
        """Store which action is no longer available."""
        super().__init__("unregistered_action", f"Action '{action}' is no longer available.")


@dataclass(frozen=True)
class Execution:
    """What ran and what it produced."""

    action: str
    parameters: dict[str, Any]
    summary: str
    result: Any


def new_execution_key() -> str:
    """The idempotency key Stripe sees for one execution, minted once at the claim."""
    return f"exec_{secrets.token_hex(8)}"


def execute_pending(
    *,
    session: Session,
    action_id: str,
    registry: Registry,
    ctx: Any,
    expected_actor: str,
) -> Execution:
    """Claim and run a pending action.

    Args:
        session: A session this function commits on its own, at each stage;
            the caller's transaction holds nothing the execution depends on.
        action_id: The id the user approved.
        registry: The same channel's registry that proposed the action.
        ctx: Handler context (a dataclass with `idempotency_key`).
        expected_actor: Who is approving; must match the proposer.

    Raises:
        UnknownAction: No such action for this actor.
        InProgress: Another approval is executing it right now.
        AlreadyDecided: The action is no longer pending.
        UnregisteredAction: The action name is no longer in the registry.
        ConfirmationError: Parameter validation failed.
        Exception: Whatever the handler raised; the action is marked failed first.
    """
    row = pending_actions.get(session, action_id)
    if row is None or row.actor != expected_actor:
        raise UnknownAction()
    if row.status == "executing":
        raise InProgress()
    key = new_execution_key()
    if not pending_actions.claim(session, action_id, idempotency_key=key):
        # The status read above may predate a concurrent claim; report what is there now.
        session.rollback()
        session.refresh(row)
        raise InProgress() if row.status == "executing" else AlreadyDecided(row.status)
    session.commit()
    return _run_claimed(session, row, registry, ctx, key, recovering=False)


def recover_executing(
    *, session: Session, action_id: str, registry: Registry, ctx: Any
) -> Execution:
    """Finish an execution a previous process died in the middle of.

    The row's stored parameters and idempotency key are reused exactly. If the
    dead process had reached Stripe, Stripe replays the original result under
    that key; if it had not, the operation happens for the first time, which
    is what the approval asked for. The handler runs with `recovering` set,
    so it does not refuse on state Stripe may already have changed.

    Raises:
        ConfirmationError: The row is not an interrupted execution.
        Exception: As `execute_pending`, from the handler.
    """
    row = pending_actions.get(session, action_id)
    if row is None or row.status != "executing" or not row.idempotency_key:
        raise ConfirmationError("not_recoverable", "That action is not an interrupted execution.")
    claimed_at = row.claimed_at or row.created_at
    if utcnow() - claimed_at > EXECUTION_RECOVERY_WINDOW:
        _park(session, row)
        raise NeedsReview(row.id, row.idempotency_key)
    return _run_claimed(session, row, registry, ctx, row.idempotency_key, recovering=True)


def _park(session: Session, row: PendingAction) -> None:
    """Land `needs_review` durably, with the key and reason in the row and the audit log.

    Nothing is sent to Stripe. The owner reads the audit entry, looks the key
    up in Stripe's request log, and either finds the operation done or knows
    it never happened; the row itself can never be approved again.
    """
    note = {
        "needs_review": True,
        "idempotency_key": row.idempotency_key,
        "reason": (
            "interrupted execution older than the recovery window; "
            "replaying the key could create a new Stripe operation"
        ),
    }
    pending_actions.park_for_review(session, row.id, note)
    audit.record(
        session, channel=row.channel, actor=row.actor, prompt=row.prompt, action=row.action,
        parameters=json.loads(row.parameters_json), result=note, mutation=True,
    )
    session.commit()


def _fail(session: Session, action_id: str, error: str) -> None:
    """Land `failed` durably before the caller re-raises.

    Whatever the handler wrote before raising is committed with it, as it
    always was. If the session itself is broken (a database error mid-handler),
    that work is discarded and the status is written on a clean transaction.
    """
    try:
        pending_actions.fail(session, action_id, error)
        session.commit()
    except Exception:
        session.rollback()
        pending_actions.fail(session, action_id, error)
        session.commit()


def _run_claimed(
    session: Session, row: PendingAction, registry: Registry, ctx: Any, key: str,
    *, recovering: bool,
) -> Execution:
    """Stages 2 and 3 for a row that is `executing` with `key` stored on it."""
    spec = registry.get(row.action)
    if spec is None:
        _fail(session, row.id, "action no longer registered")
        raise UnregisteredAction(row.action)
    try:
        parameters = json.loads(row.parameters_json)
        params = spec.params.model_validate(parameters)
    except (json.JSONDecodeError, ValidationError) as exc:
        _fail(session, row.id, str(exc))
        raise ConfirmationError(
            "invalid_stored_action",
            "That action's stored parameters are no longer valid.",
        ) from exc
    exec_ctx = dataclasses.replace(ctx, idempotency_key=key, recovering=recovering)
    try:
        result = spec.handler(exec_ctx, params)
    except Exception as exc:
        _fail(session, row.id, str(exc))
        raise
    # Stripe has answered. Recording the answer is the last transaction; if
    # even that fails (a result that will not serialise, an unwritable file),
    # the row still lands on a terminal status and is never re-approvable.
    try:
        jsonable = to_jsonable(result)
        pending_actions.finish(session, row.id, jsonable)
        audit.record(
            session,
            channel=row.channel,
            actor=row.actor,
            prompt=row.prompt,
            action=row.action,
            parameters=parameters,
            result=jsonable,
            mutation=True,
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        _fail(session, row.id, str(exc))
        raise
    return Execution(
        action=row.action, parameters=parameters, summary=row.summary, result=jsonable
    )
