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
    """The model call failed in a way the user should hear about, with a hint.

    `detail` is developer text, typically the provider's raw response body. It
    is logged by the API boundary and only sent to a client when DEBUG=1.
    """

    def __init__(self, message: str, hint: str = "", detail: str = "") -> None:
        """Store the message, an optional fix, and optional developer detail."""
        super().__init__(message)
        self.hint = hint
        self.detail = detail


class LLMBackend(Protocol):
    """A provider that completes a chat transcript into text."""

    def complete(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048
    ) -> str:
        """Return the model's text for the given system prompt and transcript."""
        ...


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first complete JSON object in a model reply.

    Tolerates code fences, prose before or after, a second object, and
    braces in trailing text, because models do all of these occasionally
    and the loop would rather recover than spend a round-trip. Each `{` is
    tried as a start until one decodes as an object; the error reported is
    the one from the earliest candidate, which is the model's actual reply.

    Raises:
        ValueError: No object could be parsed. The loop feeds this back to the
            planner as an observation so it can try again.
    """
    decoder = json.JSONDecoder()
    first_error: str | None = None
    start = text.find("{")
    while start != -1:
        try:
            parsed, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError as exc:
            first_error = first_error or exc.msg
        else:
            if isinstance(parsed, dict):
                return parsed
        start = text.find("{", start + 1)
    if first_error is not None:
        raise ValueError(f"Malformed JSON in the model reply: {first_error}")
    raise ValueError("No JSON object found in the model reply")
