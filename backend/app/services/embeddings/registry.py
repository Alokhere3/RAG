"""Embedding provider registry and factory."""

import logging
from typing import Optional

from app.core.config import Settings, get_settings
from app.services.embeddings.base import BaseEmbeddingProvider
from app.services.embeddings.deterministic import DeterministicEmbeddingProvider
from app.services.embeddings.gemini import GeminiEmbeddingProvider
from app.services.embeddings.openai import OpenAIEmbeddingProvider

logger = logging.getLogger(__name__)


def create_embedding_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    api_key: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> BaseEmbeddingProvider:
    """Factory to create embedding provider based on configuration or explicit parameters."""
    cfg = settings or get_settings()

    raw_provider = provider_name or getattr(cfg, "embedding_provider", "")
    p_name = raw_provider.strip().lower() if raw_provider else ""

    if not p_name:
        if cfg.is_production:
            raise ValueError(
                "Explicit EMBEDDING_PROVIDER is required in production environment. "
                "Silent fallback to mock/deterministic provider is forbidden."
            )
        p_name = "deterministic"

    p_model = model or getattr(cfg, "embedding_model", "")
    if not p_model:
        if p_name == "openai":
            p_model = "text-embedding-3-small"
        elif p_name == "gemini":
            p_model = "gemini-embedding-001"
        else:
            p_model = "deterministic-384"

    if dimensions is not None:
        p_dims = dimensions
    elif p_name in ("openai", "gemini"):
        p_dims = getattr(cfg, "embedding_dimensions", 1536)
    else:
        p_dims = 384

    if p_name == "openai":
        key = api_key or getattr(cfg, "openai_api_key", None)
        raw_key = key.get_secret_value() if hasattr(key, "get_secret_value") else key
        return OpenAIEmbeddingProvider(
            api_key=raw_key,
            model=p_model,
            dimensions=p_dims,
        )

    if p_name == "gemini":
        key = api_key or getattr(cfg, "gemini_api_key", None)
        raw_key = key.get_secret_value() if hasattr(key, "get_secret_value") else key
        return GeminiEmbeddingProvider(
            api_key=raw_key,
            model=p_model,
            dimensions=p_dims,
        )

    if cfg.is_production:
        raise ValueError(
            "Deterministic or mock embedding provider is not permitted in production environment."
        )

    # Default to deterministic local provider in development / test
    return DeterministicEmbeddingProvider(
        model_name=p_model,
        dimensions=p_dims,
    )
