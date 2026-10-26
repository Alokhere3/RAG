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
        migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag_prod",
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
            migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag_prod",
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
            migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag_prod",
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
            migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag_prod",
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
            migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag_prod",
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
            migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag",
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
            migration_database_url="postgresql+asyncpg://mig_user:StrongMigPass123!@db.internal:5432/rag_prod",
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


def test_production_rejects_weak_rag_app_dev_credentials():
    """Production environment rejects default rag_app_dev placeholder credentials."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
            database_url="postgresql+asyncpg://rag_app:rag_app_dev@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://rag_migrator:ProdMigPass123!@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "Default or placeholder database credentials are not permitted in production" in str(exc_info.value)


def test_production_rejects_weak_rag_migrator_dev_credentials():
    """Production environment rejects default rag_migrator_dev placeholder credentials."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
            database_url="postgresql+asyncpg://rag_app:ProdAppPass123!@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://rag_migrator:rag_migrator_dev@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "Default or placeholder migration database credentials are not permitted in production" in str(exc_info.value)


def test_production_cookie_secure_defaults_true_when_empty_string():
    """When AUTH_COOKIE_SECURE is passed as empty string (from Compose ${AUTH_COOKIE_SECURE:-}), it defaults to True in production."""
    settings = Settings(
        app_env="production",
        jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
        database_url="postgresql+asyncpg://rag_app:StrongPass123!@db.internal:5432/rag",
        migration_database_url="postgresql+asyncpg://rag_migrator:StrongPass456!@db.internal:5432/rag",
        redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
        cors_origins=["https://rag.mycompany.com"],
        auth_cookie_secure="",
        debug=False,
    )
    assert settings.auth_cookie_secure is True


def test_production_starts_cleanly_with_hardened_role_separated_settings():
    """Valid production configuration with separated roles, auth Redis, and strong secrets passes all checks."""
    settings = Settings(
        app_env="production",
        jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
        database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
        migration_database_url="postgresql+asyncpg://rag_migrator:StrongMigratorPass456!@db.internal:5432/rag",
        redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
        cors_origins=["https://rag.mycompany.com"],
        debug=False,
    )
    assert settings.is_production is True
    assert settings.auth_cookie_secure is True
    assert settings.raw_database_url == "postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag"
    assert settings.raw_migration_database_url == "postgresql+asyncpg://rag_migrator:StrongMigratorPass456!@db.internal:5432/rag"


def test_production_rejects_low_entropy_jwt_secret():
    """Production rejects repeated/trivial secrets with low character diversity."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://rag_migrator:StrongMigratorPass456!@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "trivial or repetitive" in str(exc_info.value) or "repeating pattern" in str(exc_info.value)


def test_production_rejects_repeating_cycle_jwt_secret():
    """Production rejects repeated cycle patterns like abcdabcd...."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="abcdabcdabcdabcdabcdabcdabcdabcd",
            database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://rag_migrator:StrongMigratorPass456!@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "repeating pattern" in str(exc_info.value) or "trivial" in str(exc_info.value)


def test_production_rejects_known_placeholder_jwt_secret():
    """Production rejects known placeholder values without false claims about heuristics proving randomness."""
    for placeholder in ("changeme-production-jwt-secret-key-12345", "placeholder-secret-key-for-jwt-signing-test"):
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                app_env="production",
                jwt_secret=placeholder,
                database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
                migration_database_url="postgresql+asyncpg://rag_migrator:StrongMigratorPass456!@db.internal:5432/rag",
                redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
                cors_origins=["https://rag.mycompany.com"],
                debug=False,
            )
        assert "known placeholder value" in str(exc_info.value)


def test_production_accepts_csprng_generated_secrets():
    """Production accepts legitimate CSPRNG-generated tokens (hex and urlsafe)."""
    import secrets
    hex_token = secrets.token_hex(32)  # 64 hex chars
    urlsafe_token = secrets.token_urlsafe(32)  # 43 base64 chars

    for secret in (hex_token, urlsafe_token):
        settings = Settings(
            app_env="production",
            jwt_secret=secret,
            database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://rag_migrator:StrongMigratorPass456!@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
        assert settings.is_production is True


def test_production_requires_migration_database_url_no_fallback():
    """In production, empty migration_database_url allows runtime settings but validate_migration_safety fails closed."""
    settings = Settings(
        app_env="production",
        jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
        database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
        migration_database_url="",
        redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
        cors_origins=["https://rag.mycompany.com"],
        debug=False,
    )
    assert settings.is_production is True
    with pytest.raises(ValueError) as exc_info:
        settings.validate_migration_safety()
    assert "MIGRATION_DATABASE_URL must be configured and non-empty in production" in str(exc_info.value)


def test_production_runtime_worker_starts_with_runtime_only_config():
    """Verify production background worker starts with runtime-only credentials without migration URL."""
    from app.workers.ingestion_worker import IngestionWorker

    worker_settings = Settings(
        app_env="production",
        jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
        database_url="postgresql+asyncpg://rag_app:StrongAppPass123!@db.internal:5432/rag",
        migration_database_url="",
        redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
        cors_origins=["https://rag.mycompany.com"],
        debug=False,
    )
    # Runtime worker validates production safety without needing migration credentials
    assert worker_settings.validate_production_safety() is worker_settings

    worker = IngestionWorker(worker_id="test_prod_worker")
    assert worker.worker_id == "test_prod_worker"
    assert worker.running is False


def test_production_rejects_identical_database_and_migration_urls():
    """Production rejects identical DATABASE_URL and MIGRATION_DATABASE_URL."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
            database_url="postgresql+asyncpg://rag_app:StrongPass123!@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://rag_app:StrongPass123!@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "cannot be identical" in str(exc_info.value) or "must not share the same user" in str(exc_info.value)


def test_production_rejects_same_user_for_runtime_and_migration():
    """Production rejects shared role between runtime DATABASE_URL and MIGRATION_DATABASE_URL."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            jwt_secret="StrongProductionSecretKeyThatIsAtLeast32CharsLong!",
            database_url="postgresql+asyncpg://shared_user:StrongAppPass123!@db.internal:5432/rag",
            migration_database_url="postgresql+asyncpg://shared_user:StrongMigratorPass456!@db.internal:5432/rag",
            redis_url="redis://:RedisAuthPass123!@redis.internal:6379/0",
            cors_origins=["https://rag.mycompany.com"],
            debug=False,
        )
    assert "must not share the same user" in str(exc_info.value)


def test_app_env_absent_fails_closed_outside_testing(monkeypatch):
    """When APP_ENV is absent, Settings must fail closed."""
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "Field required" in str(exc_info.value) or "app_env" in str(exc_info.value)



@pytest.mark.asyncio
async def test_production_lifespan_startup_enforces_safety_contract(monkeypatch):
    """FastAPI application lifespan startup boundary enforces production safety."""
    from app.main import app, lifespan

    # Configure invalid production environment (debug=True in production)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        async with lifespan(app):
            pass

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_worker_startup_enforces_production_safety(monkeypatch):
    """Worker entrypoint enforces production configuration before running."""
    from app.workers.ingestion_worker import main as worker_main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        await worker_main()

    get_settings.cache_clear()

