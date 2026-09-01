"""Execute a previously proposed mutation.

The stored action is the contract: approval runs exactly the parameters the
user saw, under the registry that produced them. No model is consulted here,
which is why this module cannot import an LLM.
"""

import dataclasses
import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.events import to_jsonable
from app.agent.schema import Registry
from app.db import audit, pending_actions


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
    """The action was already executed, cancelled, or failed."""

    def __init__(self, status: str) -> None:
        """Name the status so a double-click shows 'already executed', not an error."""
        super().__init__("already_decided", f"That action was already {status}.")


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


def execute_pending(
    *,
    session: Session,
    action_id: str,
    registry: Registry,
    ctx: Any,
    expected_actor: str,
    idempotency_key: str | None = None,
) -> Execution:
    """Claim and run a pending action.

    Args:
        session: Open transaction; the claim and the audit entry commit together.
        action_id: The id the user approved.
        registry: The same channel's registry that proposed the action.
        ctx: Handler context (a dataclass with `idempotency_key`).
        expected_actor: Who is approving; must match the proposer.
        idempotency_key: Client-supplied key (the `Idempotency-Key` header);
            defaults to the action id, which is itself unique per proposal.

    Raises:
        UnknownAction: No such action for this actor.
        AlreadyDecided: The action is no longer pending.
        UnregisteredAction: The action name is no longer in the registry.
        ConfirmationError: Parameter validation failed or handler raised.
        Exception: Whatever the handler raised; the action is marked failed first.
    """
    row = pending_actions.get(session, action_id)
    if row is None or row.actor != expected_actor:
        raise UnknownAction()
    if not pending_actions.claim(session, action_id):
        raise AlreadyDecided(row.status)
    spec = registry.get(row.action)
    if spec is None:
        pending_actions.fail(session, action_id, "action no longer registered")
        session.commit()
        raise UnregisteredAction(row.action)
    try:
        parameters = json.loads(row.parameters_json)
        params = spec.params.model_validate(parameters)
    except (json.JSONDecodeError, ValidationError) as exc:
        pending_actions.fail(session, action_id, str(exc))
        session.commit()
        raise ConfirmationError(
            "invalid_stored_action",
            "That action's stored parameters are no longer valid.",
        ) from exc
    exec_ctx = dataclasses.replace(ctx, idempotency_key=idempotency_key or action_id)
    try:
        result = spec.handler(exec_ctx, params)
    except Exception as exc:
        pending_actions.fail(session, action_id, str(exc))
        session.commit()
        raise
    # Stripe already ran; a failure serialising or recording the result must still
    # land the claim on a terminal status, never leave it rolled back to pending.
    try:
        jsonable = to_jsonable(result)
        pending_actions.finish(session, action_id, jsonable)
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
    except Exception as exc:
        pending_actions.fail(session, action_id, str(exc))
        session.commit()
        raise
    return Execution(
        action=row.action, parameters=parameters, summary=row.summary, result=jsonable
    )
