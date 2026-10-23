"""Unit tests for production configuration hardening (F-05 & F-07)."""

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings


def test_development_defaults_allow_local_dev():
    """Development and testing environments allow local defaults."""
    settings = Settings(
        app_env="development",
        jwt_secret="dev-secret-key-12345",
        database_url="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        redis_url="redis://localhost:6379/0",
        cors_origins=["http://localhost:3000"],
    )
    assert settings.app_env == Environment.DEVELOPMENT
    assert settings.auth_cookie_secure is False
    assert settings.is_production is False


def test_production_defaults_auth_cookie_secure_to_true():
    """In production, auth_cookie_secure defaults to True if omitted."""
    settings = Settings(
        app_env="production",
        jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
        database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
        redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
        postgres_password="StrongProdPass123!",
        cors_origins=["https://rag.mycompany.com"],
        debug=False,
    )
    assert settings.auth_cookie_secure is True
    assert settings.is_production is True


def test_production_rejects_insecure_auth_cookie():
    """Production mode must reject auth_cookie_secure=False."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
            auth_cookie_secure=False,
            debug=False,
        )
    assert "AUTH_COOKIE_SECURE must be True in production" in str(exc_info.value)


def test_production_rejects_weak_jwt_secret():
    """Production mode requires a JWT secret of at least 32 characters."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="too-short",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "JWT_SECRET must be at least 32 characters" in str(exc_info.value)


def test_production_rejects_debug_enabled():
    """Production mode must forbid debug=True."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            debug=True,
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
        )
    assert "DEBUG mode cannot be enabled in production" in str(exc_info.value)


def test_production_rejects_wildcard_cors():
    """Production mode forbids wildcard CORS."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["*"],
            debug=False,
        )
    assert "Wildcard CORS ('*') is not allowed in production" in str(exc_info.value)


def test_production_rejects_default_database_credentials():
    """Production mode rejects default placeholder database credentials."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://rag:rag@db:5432/rag",
            redis_url="redis://:SecureRedisPass!@redis.internal:6379/0",
            postgres_password="rag",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "Default or placeholder database credentials are not permitted in production" in str(exc_info.value)


def test_production_rejects_default_unauthenticated_redis():
    """Production mode rejects default unauthenticated Redis URL."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="super-strong-production-jwt-secret-minimum-32-chars",
            database_url="postgresql+asyncpg://prod_user:StrongProdPass123!@db.internal:5432/rag_prod",
            redis_url="redis://localhost:6379/0",
            postgres_password="StrongProdPass123!",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "Default unauthenticated REDIS_URL is not permitted in production" in str(exc_info.value)


def test_migration_database_url_valid_postgresql():
    """Migration database URL accepts valid PostgreSQL schemes."""
    settings = Settings(
        app_env="development",
        migration_database_url="postgresql+asyncpg://rag_migrator:pass@db:5432/rag",
    )
    assert settings.raw_migration_database_url == "postgresql+asyncpg://rag_migrator:pass@db:5432/rag"


def test_migration_database_url_empty_falls_back():
    """Empty migration_database_url falls back to runtime DATABASE_URL."""
    settings = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        migration_database_url="",
    )
    assert settings.raw_migration_database_url == "postgresql+asyncpg://rag:rag@localhost:5432/rag"


def test_migration_database_url_rejects_invalid_scheme():
    """Migration database URL rejects non-PostgreSQL schemes."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="development",
            migration_database_url="mysql://user:pass@db:3306/rag",
        )
    assert "MIGRATION_DATABASE_URL must start with a valid PostgreSQL driver scheme" in str(exc_info.value)


def test_migration_database_url_rejects_sqlite():
    """Migration database URL rejects SQLite (migrations should target PostgreSQL)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="development",
            migration_database_url="sqlite+aiosqlite:///:memory:",
        )
    assert "MIGRATION_DATABASE_URL must start with a valid PostgreSQL driver scheme" in str(exc_info.value)

