"""Settings must fail loudly, naming the missing variable and where to get it."""

import pytest

from app.settings import ConfigError, Settings


def _settings(**overrides: str) -> Settings:
    """Build Settings from explicit values, ignoring any .env on disk."""
    return Settings(_env_file=None, **overrides)


def test_missing_stripe_key_names_the_variable() -> None:
    """A blank Stripe key must produce an error that says which variable to set."""
    with pytest.raises(ConfigError) as excinfo:
        _settings(stripe_secret_key="").require_stripe()
    assert "STRIPE_SECRET_KEY" in str(excinfo.value)
    assert ".env" in str(excinfo.value)


def test_live_stripe_key_is_refused() -> None:
    """A live key must never be accepted: this project only runs against a sandbox."""
    with pytest.raises(ConfigError) as excinfo:
        _settings(stripe_secret_key="sk_live_abc").require_stripe()
    assert "test mode" in str(excinfo.value)


def test_llm_key_required_for_selected_provider_only() -> None:
    """Only the chosen provider's key is required, so a reviewer needs one key, not two."""
    _settings(llm_provider="openai", openai_api_key="sk-x").require_llm()
    with pytest.raises(ConfigError) as excinfo:
        _settings(llm_provider="anthropic", openai_api_key="sk-x").require_llm()
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_default_model_follows_provider() -> None:
    """With no LLM_MODEL override, each provider gets its documented default."""
    assert _settings(llm_provider="anthropic").resolved_model == "claude-opus-5"
    assert _settings(llm_provider="openai").resolved_model == "gpt-5.4-mini"
    assert _settings(llm_model="custom").resolved_model == "custom"
