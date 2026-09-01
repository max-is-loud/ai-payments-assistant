"""The one interface the agent uses to talk to a model.

Deliberately text-in, text-out: the planner asks for JSON in its system
prompt and `extract_json_object` parses it. That keeps both providers on an
identical code path and keeps every guardrail in Python.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    """A prior turn in the conversation as sent to the model."""

    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """The model call failed in a way the user should hear about, with a hint."""

    def __init__(self, message: str, hint: str = "") -> None:
        """Store the message and an optional fix."""
        super().__init__(message)
        self.hint = hint


class LLMBackend(Protocol):
    """A provider that completes a chat transcript into text."""

    def complete(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048
    ) -> str:
        """Return the model's text for the given system prompt and transcript."""
        ...


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply.

    Tolerates code fences and prose around the object because models do
    both occasionally, and the loop would rather recover than fail a turn.

    Raises:
        ValueError: No object could be parsed. The loop feeds this back to the
            planner as an observation so it can try again.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in the model reply")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in the model reply: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The model reply must be a JSON object")
    return parsed
