"""The LLM boundary: anything that is not a known, well-formed action is rejected."""

import pytest
from pydantic import BaseModel

from app.agent.executor import ActionError, parse_call, resolve
from app.agent.schema import ActionCall, ActionSpec, Registry


class EchoParams(BaseModel):
    """Parameters for the test-only echo action."""

    text: str
    limit: int = 20


def _echo(_ctx: object, params: EchoParams) -> dict[str, str]:
    """Return the text it was given."""
    return {"echo": params.text}


REGISTRY = Registry([ActionSpec("echo", "Echo text back", EchoParams, _echo)])


def test_malformed_call_is_rejected() -> None:
    """Wrong types or unexpected keys never reach a handler."""
    with pytest.raises(ActionError):
        parse_call({"action": 42})
    with pytest.raises(ActionError):
        parse_call({"action": "echo", "parameters": {}, "surprise": True})


def test_unknown_action_lists_the_valid_ones() -> None:
    """The error is written for the planner: it names what it may call instead."""
    with pytest.raises(ActionError, match="echo"):
        resolve(REGISTRY, ActionCall(action="read_other_customer", parameters={}))


def test_invalid_parameters_are_rejected_with_field_names() -> None:
    """Missing or mistyped parameters fail validation before execution."""
    with pytest.raises(ActionError, match="text"):
        resolve(REGISTRY, ActionCall(action="echo", parameters={}))


def test_null_parameters_mean_omitted() -> None:
    """Models send `null` for every parameter they leave unset; a default still applies."""
    call = ActionCall(action="echo", parameters={"text": "hi", "limit": None})
    _spec, params = resolve(REGISTRY, call)
    assert params.limit == 20


def test_mutation_requires_describe() -> None:
    """A mutation with no describe() could never be confirmed; refuse to register it."""
    with pytest.raises(ValueError):
        ActionSpec("boom", "x", EchoParams, _echo, mutation=True)
