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


def validate_params(model: type[BaseModel], parameters: Mapping[str, Any]) -> BaseModel:
    """Validate planner parameters, treating `null` as "not set".

    Models emit `null` for every parameter they leave unset, so a field with a
    default (`limit: int = 20`) would otherwise fail as "should be a valid
    integer" and cost a planning round-trip. Dropping the nulls before
    validation lets the model's default apply and leaves genuinely required
    fields to fail as missing. Only known fields are dropped: a `null` under a
    name the model does not have is still an unknown key, and the model's
    `extra="forbid"` must see it.

    Raises:
        ValidationError: The remaining parameters do not fit the model, or
            carry a key the model does not declare.
    """
    known = model.model_fields
    return model.model_validate(
        {k: v for k, v in parameters.items() if v is not None or k not in known}
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
        params = validate_params(spec.params, call.parameters)
    except ValidationError as exc:
        raise ActionError(f"Invalid parameters for {spec.name}: {_compact(exc)}") from exc
    return spec, params
