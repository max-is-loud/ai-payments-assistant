"""Anthropic Messages API backend."""

from collections.abc import Sequence

import anthropic

from app.llm.base import ChatMessage, LLMError


class AnthropicBackend:
    """Calls Claude with low effort: planner turns are short and latency-sensitive."""

    def __init__(self, api_key: str, model: str) -> None:
        """Create a client with a bounded timeout so a stuck call cannot hang a turn."""
        self._client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=2)
        self._model = model

    def complete(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048
    ) -> str:
        """Complete the transcript; concatenates text blocks.

        Raises:
            LLMError: Bad key, API failure, connectivity, or a refusal stop reason.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                output_config={"effort": "low"},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError(
                "Anthropic rejected the API key.", hint="Check ANTHROPIC_API_KEY in .env."
            ) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(
                f"Anthropic API error {exc.status_code}.", hint=str(exc.message)
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(
                "Could not reach the Anthropic API.",
                hint="Check your network connection.",
            ) from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        return "".join(block.text for block in response.content if block.type == "text")
