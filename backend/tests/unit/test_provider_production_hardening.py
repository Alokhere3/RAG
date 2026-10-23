"""Unit tests for explicit LLM and embedding provider enforcement in production (F-11)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services.embeddings.registry import create_embedding_provider
from app.services.llm.registry import create_llm_provider, get_default_llm_provider


def test_production_rejects_deterministic_llm_provider():
    """Production rejects explicit deterministic or mock LLM providers."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            llm_provider="deterministic",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "Deterministic or mock LLM_PROVIDER is not permitted" in str(exc_info.value)


def test_production_rejects_deterministic_embedding_provider():
    """Production rejects explicit deterministic or mock embedding providers."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            embedding_provider="deterministic",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "Deterministic or mock EMBEDDING_PROVIDER is not permitted" in str(exc_info.value)


def test_production_openai_requires_api_key():
    """Production mode requires non-empty OPENAI_API_KEY when OpenAI provider is selected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            llm_provider="openai",
            openai_api_key="",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "OPENAI_API_KEY must be configured" in str(exc_info.value)


def test_llm_registry_fails_closed_in_production():
    """LLM registry refuses to silently fall back to deterministic provider in production."""
    prod_settings = Settings(
        app_env="production",
        llm_provider="",
        jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
        database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
        redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
        postgres_password="StrongProdPass123!",
        cors_origins=["https://rag.mycompany.com"],
        debug=False,
    )

    with pytest.raises(ValueError) as exc_info:
        get_default_llm_provider(prod_settings)
    assert "Explicit LLM_PROVIDER is required in production" in str(exc_info.value)


def test_embedding_registry_fails_closed_in_production():
    """Embedding registry refuses to silently fall back to deterministic provider in production."""
    prod_settings = Settings(
        app_env="production",
        embedding_provider="",
        jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
        database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
        redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
        postgres_password="StrongProdPass123!",
        cors_origins=["https://rag.mycompany.com"],
        debug=False,
    )

    with pytest.raises(ValueError) as exc_info:
        create_embedding_provider(settings=prod_settings)
    assert "Explicit EMBEDDING_PROVIDER is required in production" in str(exc_info.value)


def test_development_allows_deterministic_providers():
    """Development and testing environments allow deterministic providers without error."""
    dev_settings = Settings(
        app_env="development",
        llm_provider="deterministic",
        embedding_provider="deterministic",
        jwt_secret="dev-secret-key-12345",
    )
    llm = get_default_llm_provider(dev_settings)
    assert llm.name == "deterministic"

    emb = create_embedding_provider(provider_name="deterministic", settings=dev_settings)
    assert emb.name == "deterministic"
