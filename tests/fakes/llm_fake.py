"""A scripted LLM: returns canned responses in order and records every call."""

from collections.abc import Sequence

from app.llm.base import ChatMessage


class ScriptedLLM:
    """Pops one scripted response per `complete()`; fails loudly when the script runs out."""

    def __init__(self, responses: Sequence[str]) -> None:
        """Queue the responses the test expects the planner to produce."""
        self._responses = list(responses)
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def complete(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048
    ) -> str:
        """Return the next scripted response."""
        self.calls.append((system, list(messages)))
        if not self._responses:
            raise AssertionError("Unexpected LLM call: the script is exhausted")
        return self._responses.pop(0)
