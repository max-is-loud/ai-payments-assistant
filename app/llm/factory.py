"""Pick a backend from settings."""

from app.llm.anthropic_backend import AnthropicBackend
from app.llm.base import LLMBackend
from app.llm.openai_backend import OpenAIBackend
from app.settings import Settings


def build_backend(settings: Settings) -> LLMBackend:
    """Instantiate the provider named by LLM_PROVIDER with its resolved model."""
    if settings.llm_provider == "anthropic":
        return AnthropicBackend(settings.anthropic_api_key, settings.resolved_model)
    return OpenAIBackend(settings.openai_api_key, settings.resolved_model)
