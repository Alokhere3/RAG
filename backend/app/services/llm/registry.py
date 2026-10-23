"""Registry and factory for constructing configured LLM inference providers."""

from typing import Optional

from app.core.config import Settings, get_settings
from app.services.llm.base import BaseLlmProvider
from app.services.llm.deterministic import DeterministicLlmProvider
from app.services.llm.openai import OpenAILlmProvider


def create_llm_provider(
    provider_name: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_seconds: float = 30.0,
    max_retries: int = 3,
) -> BaseLlmProvider:
    """Instantiate an LLM provider adapter by name."""
    clean_name = provider_name.strip().lower()

    if clean_name in ("deterministic", "mock", "test"):
        settings = get_settings()
        if settings.is_production:
            raise ValueError(
                "Deterministic or mock LLM provider is not permitted in production environment."
            )
        return DeterministicLlmProvider(model_name=model or "deterministic-llm-v1")

    if clean_name == "openai":
        return OpenAILlmProvider(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

    raise ValueError(f"Unsupported LLM provider: '{provider_name}'. Supported: deterministic, openai")


def get_default_llm_provider(settings: Optional[Settings] = None) -> BaseLlmProvider:
    """Build the application default LLM provider from settings."""
    cfg = settings or get_settings()
    provider_name = cfg.llm_provider.strip() if cfg.llm_provider else ""

    if not provider_name:
        if cfg.is_production:
            raise ValueError(
                "Explicit LLM_PROVIDER is required in production environment. "
                "Silent fallback to mock/deterministic provider is forbidden."
            )
        provider_name = "deterministic"

    raw_key = cfg.openai_api_key.get_secret_value() if cfg.openai_api_key else None

    return create_llm_provider(
        provider_name=provider_name,
        model=cfg.llm_model or None,
        api_key=raw_key,
    )
