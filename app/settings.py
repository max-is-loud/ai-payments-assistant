"""Process configuration loaded from the environment.

Every entrypoint (API, bot, seed) validates only the settings it needs, so a
reviewer running the seed script is never asked for a Telegram token. Errors
name the variable and where to obtain it.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-opus-5", "openai": "gpt-5.4-mini"}


class ConfigError(RuntimeError):
    """A required setting is missing or invalid; the message says how to fix it."""


class Settings(BaseSettings):
    """All configuration, read from the environment and a repo-root .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    stripe_secret_key: str = ""
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = ""
    telegram_bot_token: str = ""
    owner_api_token: str = ""
    database_url: str = "sqlite:///./data/assistant.db"

    @property
    def resolved_model(self) -> str:
        """The model to call: the override if set, else the provider's default."""
        return self.llm_model or DEFAULT_MODELS[self.llm_provider]

    def require_stripe(self) -> None:
        """Fail unless a Stripe *test* key is configured.

        Raises:
            ConfigError: Missing key, or a live key. A live key is refused
                outright because the seed script creates charges.
        """
        if not self.stripe_secret_key or self.stripe_secret_key == "sk_test_replace_me":
            raise ConfigError(
                "Set STRIPE_SECRET_KEY in .env — Stripe Dashboard → Developers → API keys "
                "(test mode)."
            )
        if not self.stripe_secret_key.startswith("sk_test_"):
            raise ConfigError(
                "STRIPE_SECRET_KEY must be a test mode key (sk_test_...). "
                "This project never runs against live data."
            )

    def require_llm(self) -> None:
        """Fail unless the selected provider has a key.

        Raises:
            ConfigError: Names the key for the configured LLM_PROVIDER only.
        """
        key = self.anthropic_api_key if self.llm_provider == "anthropic" else self.openai_api_key
        if not key:
            variable = "ANTHROPIC_API_KEY" if self.llm_provider == "anthropic" else "OPENAI_API_KEY"
            url = (
                "https://console.anthropic.com"
                if self.llm_provider == "anthropic"
                else "https://platform.openai.com"
            )
            raise ConfigError(f"Set {variable} in .env (LLM_PROVIDER={self.llm_provider}) — {url}")

    def require_telegram(self) -> None:
        """Fail unless a bot token is configured.

        Raises:
            ConfigError: With the BotFather pointer.
        """
        if not self.telegram_bot_token:
            raise ConfigError("Set TELEGRAM_BOT_TOKEN in .env — create a bot with @BotFather.")

    def require_owner_token(self) -> None:
        """Fail unless the owner API token is configured.

        Raises:
            ConfigError: The .env.example default is fine for local use.
        """
        if not self.owner_api_token:
            raise ConfigError("Set OWNER_API_TOKEN in .env (copy .env.example for a default).")


def load_settings() -> Settings:
    """Read settings from the environment and .env."""
    return Settings()
