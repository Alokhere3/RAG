"""Unit tests for configuration validation and production safety hardening."""

import pytest
from pydantic import ValidationError, SecretStr

from app.core.config import Environment, Settings, get_settings


def test_settings_load_defaults():
    """Ensure default settings load successfully with appropriate defaults."""
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        redis_url="redis://localhost:6379/0",
    )
    assert settings.app_name == "RAG Platform"
    assert settings.app_version == "0.1.0"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.organization_name == "Demo Organization"
    assert settings.bot_name == "AI Assistant"
    assert settings.assistant_name == "AI Assistant"
    assert settings.primary_color == "#2563EB"
    assert settings.secondary_color == "#1E293B"
    assert settings.accent_color == "#3B82F6"
    assert settings.enable_chat is False
    assert settings.enable_documents is False
    assert settings.app_env == Environment.TESTING
    assert settings.is_testing is True
    assert settings.is_production is False


def test_valid_development_configuration():
    """Ensure development environment allows debug and wildcard CORS."""
    dev_settings = Settings(
        app_env="development",
        debug=True,
        cors_origins=["*"],
    )
    assert dev_settings.is_development is True
    assert dev_settings.debug is True
    assert "*" in dev_settings.parsed_cors_origins


def test_valid_production_configuration():
    """Ensure valid production settings with explicit origins and secret pass validation."""
    prod_settings = Settings(
        app_env="production",
        debug=False,
        cors_origins=["https://client.app.com", "https://admin.app.com"],
        jwt_secret="super-strong-production-secret-token",
        database_url="postgresql+asyncpg://prod_user:prod_pass@db.prod:5432/rag_prod",
        migration_database_url="postgresql+asyncpg://mig_user:mig_pass@db.prod:5432/rag_prod",
        redis_url="redis://:redis_pass@redis.prod:6379/0",
    )
    assert prod_settings.is_production is True
    assert prod_settings.debug is False
    assert prod_settings.parsed_cors_origins == ["https://client.app.com", "https://admin.app.com"]
    assert prod_settings.raw_database_url == "postgresql+asyncpg://prod_user:prod_pass@db.prod:5432/rag_prod"
    assert prod_settings.raw_migration_database_url == "postgresql+asyncpg://mig_user:mig_pass@db.prod:5432/rag_prod"
    assert prod_settings.raw_redis_url == "redis://:redis_pass@redis.prod:6379/0"


def test_production_debug_rejection():
    """Ensure production environment strictly rejects DEBUG=true."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            debug=True,
            cors_origins=["https://app.client.com"],
            jwt_secret="secret",
        )
    assert "DEBUG mode cannot be enabled in production environment" in str(exc_info.value)


def test_production_wildcard_cors_rejection():
    """Ensure production environment strictly rejects wildcard CORS."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            debug=False,
            cors_origins="*",
            jwt_secret="secret",
        )
    assert "Wildcard CORS ('*') is not allowed in production environment" in str(exc_info.value)


def test_production_sqlite_rejection():
    """Ensure production environment rejects SQLite databases."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            debug=False,
            cors_origins=["https://client.com"],
            jwt_secret="secret",
            database_url="sqlite+aiosqlite:///:memory:",
        )
    assert "SQLite database cannot be used in production environment" in str(exc_info.value)


def test_production_missing_jwt_secret():
    """Ensure production environment rejects empty JWT secret."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            debug=False,
            cors_origins=["https://client.com"],
            jwt_secret="",
        )
    assert "JWT_SECRET must be configured and non-empty in production environment" in str(exc_info.value)


def test_invalid_environment():
    """Ensure invalid environment strings are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="invalid_env")
    assert "Invalid environment 'invalid_env'" in str(exc_info.value)


def test_invalid_database_url():
    """Ensure database_url validator rejects invalid database driver schemes."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="test",
            database_url="mysql://user:pass@localhost:3306/db",
            redis_url="redis://localhost:6379/0",
        )
    assert "DATABASE_URL must start with a valid" in str(exc_info.value)


def test_invalid_redis_url():
    """Ensure redis_url validator rejects invalid redis schemes."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="test",
            database_url="postgresql+asyncpg://rag:rag@localhost:5432/rag",
            redis_url="http://localhost:6379",
        )
    assert "REDIS_URL must start with redis:// or rediss://" in str(exc_info.value)


def test_invalid_port_range():
    """Ensure port validator enforces 1-65535."""
    with pytest.raises(ValidationError):
        Settings(
            app_env="test",
            port=99999,
        )


def test_color_validation():
    """Ensure hex color validator enforces valid #RGB and #RRGGBB formats."""
    valid_settings = Settings(
        app_env="test",
        primary_color="#10B981",
        secondary_color="#0F172A",
        accent_color="#F59E0B",
    )
    assert valid_settings.primary_color == "#10B981"

    valid_short = Settings(
        app_env="test",
        primary_color="#FFF",
    )
    assert valid_short.primary_color == "#FFF"

    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="test", primary_color="blue")
    assert "must be a valid hex color code" in str(exc_info.value)

    with pytest.raises(ValidationError):
        Settings(app_env="test", secondary_color="123456")

    with pytest.raises(ValidationError):
        Settings(app_env="test", accent_color="#12345")


def test_url_validation():
    """Ensure optional branding URLs are validated for safe schemes."""
    valid = Settings(
        app_env="test",
        organization_logo_url="https://example.com/logo.png",
        organization_website_url="http://example.com",
        assistant_avatar_url="/assets/avatar.png",
        favicon_url="/favicon.ico",
    )
    assert valid.organization_logo_url == "https://example.com/logo.png"
    assert valid.assistant_avatar_url == "/assets/avatar.png"

    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="test", organization_logo_url="javascript:alert(1)")
    assert "must be an absolute URL" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env="test", favicon_url="ftp://files.com/fav.ico")
    assert "must be an absolute URL" in str(exc_info.value)


def test_secret_masking():
    """Ensure SecretStr fields mask credentials in string and repr output."""
    raw_db = "postgresql+asyncpg://admin:super_secret_password@db.org:5432/rag"
    raw_redis = "redis://:redis_secret_password@cache.org:6379/0"
    raw_jwt = "super_secret_jwt_key"

    settings = Settings(
        app_env="test",
        database_url=raw_db,
        redis_url=raw_redis,
        jwt_secret=raw_jwt,
    )

    # SecretStr masking in str() and repr()
    assert str(settings.database_url) == "**********"
    assert str(settings.redis_url) == "**********"
    assert str(settings.jwt_secret) == "**********"
    assert "super_secret_password" not in repr(settings.database_url)
    assert "redis_secret_password" not in repr(settings.redis_url)
    assert "super_secret_jwt_key" not in repr(settings.jwt_secret)

    # settings repr must not expose secrets
    settings_repr = repr(settings)
    assert "super_secret_password" not in settings_repr
    assert "redis_secret_password" not in settings_repr
    assert "super_secret_jwt_key" not in settings_repr

    # Raw getters return plain string
    assert settings.raw_database_url == raw_db
    assert settings.raw_redis_url == raw_redis
    assert settings.jwt_secret.get_secret_value() == raw_jwt


def test_settings_caching():
    """Ensure get_settings() returns a cached singleton and cache_clear works."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2

    get_settings.cache_clear()
    s3 = get_settings()
    assert s3 is not None


def test_backward_compatible_aliases():
    """Ensure Phase 0 field names synchronize with Phase 1 field names."""
    s1 = Settings(app_env="test", bot_name="Enterprise Bot")
    assert s1.assistant_name == "Enterprise Bot"
    assert s1.bot_name == "Enterprise Bot"

    s2 = Settings(app_env="test", assistant_name="Support Agent")
    assert s2.bot_name == "Support Agent"
    assert s2.assistant_name == "Support Agent"

    s3 = Settings(app_env="test", logo_url="/brand/logo.png")
    assert s3.organization_logo_url == "/brand/logo.png"

    s4 = Settings(app_env="test", organization_logo_url="/tenant/logo.svg")
    assert s4.logo_url == "/tenant/logo.svg"


def test_cors_origins_parsing():
    """Ensure cors_origins supports both list and comma-separated string."""
    s_list = Settings(app_env="test", cors_origins=["http://localhost:3000", "http://example.com"])
    assert s_list.parsed_cors_origins == ["http://localhost:3000", "http://example.com"]

    s_str = Settings(app_env="test", cors_origins="http://localhost:3001, https://app.client.com")
    assert s_str.parsed_cors_origins == ["http://localhost:3001", "https://app.client.com"]


def test_to_public_config_contract():
    """Ensure to_public_config constructs a clean, secret-free PublicConfigResponse."""
    settings = Settings(
        app_env="testing",
        app_name="Acme Knowledge",
        app_version="1.2.0",
        organization_name="Acme Corp",
        organization_logo_url="https://acme.com/logo.svg",
        organization_website_url="https://acme.com",
        assistant_name="Acme Assistant",
        assistant_description="Answers Acme questions",
        assistant_avatar_url="https://acme.com/avatar.png",
        primary_color="#047857",
        secondary_color="#064E3B",
        accent_color="#34D399",
        favicon_url="https://acme.com/favicon.ico",
        enable_chat=True,
        enable_documents=False,
        database_url="postgresql+asyncpg://super_user:secret_pass@db.internal:5432/acme_db",
        redis_url="redis://:redis_secret@redis.internal:6379/0",
        jwt_secret="super-confidential-secret-key",
        openai_api_key="sk-proj-super-secret-key",
    )

    public_config = settings.to_public_config()

    assert public_config.application.name == "Acme Knowledge"
    assert public_config.application.version == "1.2.0"
    assert public_config.application.environment == "testing"

    assert public_config.organization.name == "Acme Corp"
    assert public_config.organization.logo_url == "https://acme.com/logo.svg"
    assert public_config.organization.website_url == "https://acme.com"

    assert public_config.assistant.name == "Acme Assistant"
    assert public_config.assistant.description == "Answers Acme questions"
    assert public_config.assistant.avatar_url == "https://acme.com/avatar.png"

    assert public_config.branding.primary_color == "#047857"
    assert public_config.branding.secondary_color == "#064E3B"
    assert public_config.branding.accent_color == "#34D399"
    assert public_config.branding.favicon_url == "https://acme.com/favicon.ico"

    assert public_config.features.chat is True
    assert public_config.features.documents is False

    serialized = public_config.model_dump(by_alias=True)
    assert "logoUrl" in serialized["organization"]
    assert "websiteUrl" in serialized["organization"]
    assert "avatarUrl" in serialized["assistant"]
    assert "primaryColor" in serialized["branding"]
    assert "secondaryColor" in serialized["branding"]
    assert "accentColor" in serialized["branding"]
    assert "faviconUrl" in serialized["branding"]

    serialized_str = str(serialized)
    assert "super_user" not in serialized_str
    assert "secret_pass" not in serialized_str
    assert "db.internal" not in serialized_str
    assert "redis_secret" not in serialized_str
    assert "super-confidential" not in serialized_str
    assert "sk-proj" not in serialized_str


def test_settings_fails_when_app_env_missing(monkeypatch):
    """Verify Settings() strictly requires explicit app_env and fails closed if missing."""
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("app_env",) for err in errors), f"Expected missing app_env error, got: {errors}"


def test_settings_fails_even_if_pytest_env_var_present(monkeypatch):
    """Verify presence of PYTEST_CURRENT_TEST cannot bypass app_env requirement or turn it into testing default."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/unit/test_config.py::test_dummy (call)")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("app_env",) for err in errors), f"Expected missing app_env error, got: {errors}"


def test_settings_fails_when_app_env_empty(monkeypatch):
    """Verify Settings() strictly rejects explicitly empty APP_ENV string."""
    monkeypatch.setenv("APP_ENV", "")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    errors = exc_info.value.errors()
    assert any(
        err["loc"] == ("app_env",) and "APP_ENV must be explicitly configured and non-empty" in err["msg"]
        for err in errors
    ), f"Expected non-empty APP_ENV validation error, got: {errors}"


def test_settings_fails_when_app_env_whitespace(monkeypatch):
    """Verify Settings() strictly rejects whitespace-only APP_ENV string."""
    monkeypatch.setenv("APP_ENV", "   ")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    errors = exc_info.value.errors()
    assert any(
        err["loc"] == ("app_env",) and "APP_ENV must be explicitly configured and non-empty" in err["msg"]
        for err in errors
    ), f"Expected non-empty APP_ENV validation error, got: {errors}"


def test_settings_fails_when_app_env_none():
    """Verify Settings() strictly rejects app_env=None explicitly passed."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, app_env=None)
    errors = exc_info.value.errors()
    assert any(
        err["loc"] == ("app_env",) and "APP_ENV must be explicitly configured and non-empty" in err["msg"]
        for err in errors
    ), f"Expected non-empty APP_ENV validation error, got: {errors}"


def test_settings_valid_development_value():
    """Verify Settings() accepts valid development APP_ENV and configures development mode."""
    settings = Settings(_env_file=None, app_env="development")
    assert settings.app_env == Environment.DEVELOPMENT
    assert settings.is_development is True
    assert settings.is_production is False
    assert settings.is_testing is False


def test_settings_valid_production_value():
    """Verify Settings() accepts valid production APP_ENV with required production credentials."""
    settings = Settings(
        _env_file=None,
        app_env="production",
        debug=False,
        cors_origins=["https://dashboard.example.com"],
        jwt_secret="super-strong-production-secret-token-32-chars",
        database_url="postgresql+asyncpg://app_user:app_pass@127.0.0.1:5432/rag_prod",
        migration_database_url="postgresql+asyncpg://mig_user:mig_pass@127.0.0.1:5432/rag_prod",
        redis_url="redis://:redis_pass@127.0.0.1:6379/0",
        auth_cookie_secure=True,
    )
    assert settings.app_env == Environment.PRODUCTION
    assert settings.is_production is True
    assert settings.is_development is False
    assert settings.is_testing is False
