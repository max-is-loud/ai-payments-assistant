"""Typed events the loop emits, and JSON coercion for results."""

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal[
    "planning", "action", "observation", "confirmation", "answer", "clarify", "error"
]


@dataclass(frozen=True)
class AgentEvent:
    """One step of the agent's work, streamable as an SSE event."""

    type: EventType
    data: dict[str, Any]


def to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses, models, and dates into JSON-safe values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    return value
