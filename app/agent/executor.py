"""Validation at the LLM boundary. Nothing unvalidated reaches a handler."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agent.schema import ActionCall, ActionSpec, Registry


class ActionError(Exception):
    """A recoverable problem, phrased for the planner, returned as an observation."""


def _compact(exc: ValidationError) -> str:
    """Render pydantic errors as `field: message` pairs."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'body'}: {err['msg']}" for err in exc.errors()
    )


def parse_call(raw: Mapping[str, Any]) -> ActionCall:
    """Validate the shape of a planner step.

    Raises:
        ActionError: The object is not `{reasoning?, action, parameters?}`.
    """
    try:
        return ActionCall.model_validate(dict(raw))
    except ValidationError as exc:
        raise ActionError(f"Malformed action: {_compact(exc)}") from exc


def resolve(registry: Registry, call: ActionCall) -> tuple[ActionSpec, BaseModel]:
    """Find the action and validate its parameters.

    Raises:
        ActionError: Unknown action (lists the valid names) or invalid parameters.
    """
    spec = registry.get(call.action)
    if spec is None:
        valid_actions = ", ".join(registry.names() + ["answer", "clarify"])
        raise ActionError(f"Unknown action '{call.action}'. Valid actions: {valid_actions}")
    try:
        params = spec.params.model_validate(call.parameters)
    except ValidationError as exc:
        raise ActionError(f"Invalid parameters for {spec.name}: {_compact(exc)}") from exc
    return spec, params
