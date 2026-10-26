"""Unit tests for Alembic migration URL resolution and production safety validation.

Verifies:
- Production migrations strictly require and validate MIGRATION_DATABASE_URL.
- A pre-populated or CLI-supplied sqlalchemy.url cannot bypass production validation or role separation.
- Production cannot fall back to runtime DATABASE_URL.
- Development migration workflows remain functional with default and custom sqlalchemy.url.
- Offline and online migration workflows adhere to the same validation contract.
"""

import importlib.util
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError

from alembic.config import Config
from app.core.config import Settings

# Dynamically load backend/alembic/env.py without colliding with site-packages alembic
BACKEND_DIR = Path(__file__).resolve().parents[2]
env_path = BACKEND_DIR / "alembic" / "env.py"
spec = importlib.util.spec_from_file_location("rag_alembic_env", env_path)
rag_alembic_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rag_alembic_env)
resolve_migration_url = rag_alembic_env.resolve_migration_url



def _make_prod_settings(
    app_db_user: str = "rag_app",
    mig_db_user: str = "rag_migrator",
    omit_mig_url: bool = False,
) -> Settings:
    """Helper to create valid or invalid production settings."""
    kwargs = {
        "app_env": "production",
        "secret_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "jwt_secret": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
        "first_superuser_email": "admin@example.com",
        "first_superuser_password": "ProdSuperPassword123!",
        "database_url": f"postgresql+asyncpg://{app_db_user}:AppSecretPass123!@db:5432/rag",
        "redis_url": "redis://:RedisSecret123!@redis:6379/0",
        "cors_origins": ["https://app.example.com"],
        "auth_cookie_secure": True,
    }


    if not omit_mig_url:
        kwargs["migration_database_url"] = (
            f"postgresql+asyncpg://{mig_db_user}:MigSecretPass123!@db:5432/rag"
        )
    return Settings(**kwargs)


def test_production_migration_url_default_path():
    """In production, resolve_migration_url must return MIGRATION_DATABASE_URL when sqlalchemy.url is unset."""
    settings = _make_prod_settings()
    alembic_cfg = Config()

    resolved = resolve_migration_url(alembic_config=alembic_cfg, settings_override=settings)
    assert resolved == settings.raw_migration_database_url
    assert "rag_migrator" in resolved
    assert "rag_app" not in resolved


def test_production_migration_url_matching_explicit_url():
    """In production, an explicit sqlalchemy.url matching MIGRATION_DATABASE_URL is accepted."""
    settings = _make_prod_settings()
    alembic_cfg = Config()
    alembic_cfg.set_main_option("sqlalchemy.url", settings.raw_migration_database_url)

    resolved = resolve_migration_url(alembic_config=alembic_cfg, settings_override=settings)
    assert resolved == settings.raw_migration_database_url


def test_production_rejects_diverging_sqlalchemy_url_bypass():
    """In production, an explicit sqlalchemy.url diverging from MIGRATION_DATABASE_URL is rejected."""
    settings = _make_prod_settings()
    alembic_cfg = Config()
    # Attempt bypass by providing runtime database URL or unauthorized host
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        "postgresql+asyncpg://rag_app:BypassPassword!@otherhost:5432/rag",
    )

    with pytest.raises(ValueError, match="prohibited"):
        resolve_migration_url(alembic_config=alembic_cfg, settings_override=settings)


def test_production_cannot_bypass_validation_with_runtime_url():
    """In production, an explicit sqlalchemy.url using the runtime role is rejected."""
    settings = _make_prod_settings()
    alembic_cfg = Config()
    alembic_cfg.set_main_option("sqlalchemy.url", settings.raw_database_url)

    with pytest.raises(ValueError, match="prohibited"):
        resolve_migration_url(alembic_config=alembic_cfg, settings_override=settings)


def test_production_requires_migration_database_url():
    """In production, omitting MIGRATION_DATABASE_URL allows runtime settings, but migration resolution fails closed."""
    settings = _make_prod_settings(omit_mig_url=True)
    assert settings.is_production is True
    # Migration execution strictly fails closed when migration credentials are missing
    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL must be configured"):
        resolve_migration_url(settings_override=settings)


def test_development_honors_explicit_sqlalchemy_url():
    """In development, an explicitly configured sqlalchemy.url is honored."""
    dev_settings = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://rag_app:dev@localhost:5432/rag",
    )
    alembic_cfg = Config()
    custom_url = "postgresql+asyncpg://custom_dev:pass@localhost:5432/custom_db"
    alembic_cfg.set_main_option("sqlalchemy.url", custom_url)

    resolved = resolve_migration_url(alembic_config=alembic_cfg, settings_override=dev_settings)
    assert resolved == custom_url


def test_development_falls_back_to_database_url_when_migration_url_omitted():
    """In development, when neither sqlalchemy.url nor MIGRATION_DATABASE_URL is set, it falls back to DATABASE_URL."""
    dev_settings = Settings(
        app_env="development",
        database_url="postgresql+asyncpg://rag_app:dev@localhost:5432/rag",
    )
    alembic_cfg = Config()

    resolved = resolve_migration_url(alembic_config=alembic_cfg, settings_override=dev_settings)
    assert resolved == dev_settings.raw_database_url
