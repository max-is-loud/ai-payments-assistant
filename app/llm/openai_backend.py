"""OpenAI Chat Completions backend."""

from collections.abc import Sequence

import openai

from app.llm.base import ChatMessage, LLMError


class OpenAIBackend:
    """Calls an OpenAI chat model with the system prompt as the first message."""

    def __init__(self, api_key: str, model: str) -> None:
        """Create a client with a bounded timeout."""
        self._client = openai.OpenAI(api_key=api_key, timeout=60.0, max_retries=2)
        self._model = model

    def complete(
        self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048
    ) -> str:
        """Complete the transcript.

        Raises:
            LLMError: Bad key, API failure, or connectivity.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    *({"role": m.role, "content": m.content} for m in messages),
                ],
                max_completion_tokens=max_tokens,
            )
        except openai.AuthenticationError as exc:
            raise LLMError(
                "OpenAI rejected the API key.", hint="Check OPENAI_API_KEY in .env."
            ) from exc
        except openai.APIStatusError as exc:
            raise LLMError(
                f"OpenAI API error {exc.status_code}.", hint=str(exc.message)
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMError(
                "Could not reach the OpenAI API.",
                hint="Check your network connection.",
            ) from exc
        return response.choices[0].message.content or ""
