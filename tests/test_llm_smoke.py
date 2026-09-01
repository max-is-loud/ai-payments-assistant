"""One real call per provider, deselected by default. Nondeterministic assertions are theatre."""

import pytest

from app.llm.base import ChatMessage, extract_json_object
from app.llm.factory import build_backend
from app.settings import ConfigError, Settings


@pytest.mark.live_llm
def test_configured_backend_returns_parseable_json() -> None:
    """The configured provider answers a trivial JSON request end to end."""
    settings = Settings()
    try:
        settings.require_llm()
    except ConfigError as exc:
        pytest.skip(str(exc))
    backend = build_backend(settings)
    text = backend.complete(
        system='Reply with exactly this JSON and nothing else: {"ok": true}',
        messages=[ChatMessage(role="user", content="go")],
        max_tokens=64,
    )
    assert extract_json_object(text) == {"ok": True}
