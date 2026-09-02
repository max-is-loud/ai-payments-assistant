"""Provider failures reach the owner as a sentence and a fix; the SDK's body is developer detail."""

from typing import Any

import anthropic
import httpx
import openai
import pytest

from app.llm.anthropic_backend import AnthropicBackend
from app.llm.base import ChatMessage, LLMError
from app.llm.openai_backend import OpenAIBackend

BODY = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad request"}}
SDK_TEXT = f"Error code: 400 - {BODY}"
"""How both SDKs word a status error: the status, then the raw JSON body."""


def _response(status: int) -> httpx.Response:
    """The bare HTTP response the SDK exception types require."""
    return httpx.Response(status, request=httpx.Request("POST", "https://api.example.test"))


def _complete(backend: AnthropicBackend | OpenAIBackend) -> str:
    """One planner call."""
    return backend.complete(system="s", messages=[ChatMessage(role="user", content="go")])


def _assert_body_is_detail_only(error: LLMError) -> None:
    """The JSON body is in `detail`, and nowhere the owner reads."""
    assert "{" not in str(error) and "{" not in error.hint
    assert error.hint, "a status error still deserves a next step"
    assert error.detail == SDK_TEXT


def test_anthropic_status_error_keeps_the_sdk_body_out_of_the_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hint used to be the SDK message verbatim, which is a JSON body on the owner's screen."""
    backend = AnthropicBackend("sk-ant-test", "claude-test")

    def boom(**_kwargs: Any) -> Any:
        """What the SDK raises for a 4xx/5xx."""
        raise anthropic.APIStatusError(SDK_TEXT, response=_response(400), body=BODY)

    monkeypatch.setattr(backend._client.messages, "create", boom)
    with pytest.raises(LLMError) as excinfo:
        _complete(backend)
    _assert_body_is_detail_only(excinfo.value)


def test_openai_status_error_keeps_the_sdk_body_out_of_the_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same contract for the second provider, so switching LLM_PROVIDER changes nothing here."""
    backend = OpenAIBackend("sk-test", "gpt-test")

    def boom(**_kwargs: Any) -> Any:
        """What the SDK raises for a 4xx/5xx."""
        raise openai.APIStatusError(SDK_TEXT, response=_response(400), body=BODY)

    monkeypatch.setattr(backend._client.chat.completions, "create", boom)
    with pytest.raises(LLMError) as excinfo:
        _complete(backend)
    _assert_body_is_detail_only(excinfo.value)
