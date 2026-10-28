"""Centralized Application Configuration.

Implements Pydantic Settings with strong typing, environment variable loading,
and validation rules conforming to Phase 0 and Phase 1 architecture.
"""

from enum import Enum
from functools import lru_cache
import os
import re
from typing import Any, List, Union
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_core import core_schema
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.config import (
    ApplicationPublicConfig,
    AssistantPublicConfig,
    BrandingPublicConfig,
    FeaturesPublicConfig,
    OrganizationPublicConfig,
    PublicConfigResponse,
)

HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class SecretString(str):
    """Masked string adapter that protects secrets from logs while preserving string API compatibility."""

    def __repr__(self) -> str:
        return "SecretString('**********')"

    def __str__(self) -> str:
        return "**********"

    def get_secret_value(self) -> str:
        """Return the unmasked raw secret value."""
        return super().__str__()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: "**********",
                info_arg=False,
                return_schema=core_schema.str_schema(),
            ),
        )


class Environment(str, Enum):
    """Allowed deployment environment names."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Central application settings object."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application Layer
    # -------------------------------------------------------------------------
    app_env: Environment = Field(
        description="Deployment environment name [development, testing, staging, production]",
    )

    app_name: str = Field(
        default="RAG Platform",
        description="Public platform identifier",
    )
    app_version: str = Field(
        default="0.1.0",
        description="Semantic application version",
    )
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="Prefix for v1 REST endpoints",
    )
    debug: bool = Field(
        default=False,
        description="Toggle verbose debug output and reload",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging verbosity level",
    )
    port: int = Field(
        default=8001,
        ge=1,
        le=65535,
        description="Listening HTTP port",
    )
    host: str = Field(
        default="0.0.0.0",
        description="Listening host interface",
    )

    # -------------------------------------------------------------------------
    # Organization / White-Label Layer
    # -------------------------------------------------------------------------
    organization_name: str = Field(
        default="Demo Organization",
        description="White-label tenant / company name",
    )
    organization_logo_url: str = Field(
        default="",
        description="URL for tenant header/branding logo",
    )
    organization_website_url: str = Field(
        default="",
        description="Tenant website URL",
    )
    # Phase 0 backward compatibility alias
    logo_url: str = Field(
        default="",
        description="Alias for organization_logo_url (Phase 0 compatibility)",
    )

    # -------------------------------------------------------------------------
    # Assistant / Persona Layer
    # -------------------------------------------------------------------------
    assistant_name: str = Field(
        default="AI Assistant",
        description="Display name of assistant",
    )
    assistant_description: str = Field(
        default="Ask questions about your organization's knowledge.",
        description="Brief introductory description or tagline for the assistant",
    )
    assistant_avatar_url: str = Field(
        default="",
        description="URL for assistant avatar image",
    )
    # Phase 0 backward compatibility alias
    bot_name: str = Field(
        default="AI Assistant",
        description="Alias for assistant_name (Phase 0 compatibility)",
    )

    # -------------------------------------------------------------------------
    # Visual Theme & Branding Layer
    # -------------------------------------------------------------------------
    primary_color: str = Field(
        default="#2563EB",
        description="Theme hex color code for primary accents",
    )
    secondary_color: str = Field(
        default="#1E293B",
        description="Theme hex color code for secondary surfaces",
    )
    accent_color: str = Field(
        default="#3B82F6",
        description="Theme hex color code for highlight accents",
    )
    favicon_url: str = Field(
        default="",
        description="URL for browser favicon icon",
    )

    # -------------------------------------------------------------------------
    # API & Network Layer
    # -------------------------------------------------------------------------
    cors_origins: Union[List[str], str] = Field(
        default=["*"],
        description="Allowed CORS origins as list or comma-separated string",
    )

    # -------------------------------------------------------------------------
    # Feature Flags (Public UI Controls)
    # -------------------------------------------------------------------------
    enable_chat: bool = Field(
        default=False,
        description="Toggle chat interface visibility",
    )
    enable_documents: bool = Field(
        default=False,
        description="Toggle document management interface visibility",
    )
    enable_ingestion: bool = Field(
        default=True,
        description="Toggle document ingestion pipeline",
    )
    parser_max_pages: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Max pages permitted to extract per document",
    )
    parser_max_chars: int = Field(
        default=2000000,
        ge=100,
        le=50000000,
        description="Max extracted characters per document",
    )
    parser_timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Max timeout for document parser execution in seconds",
    )
    ingestion_lease_seconds: int = Field(
        default=120,
        ge=10,
        le=3600,
        description="Lease timeout duration in seconds for ingestion workers",
    )

    # -------------------------------------------------------------------------
    # Private Server Infrastructure (Layer A — Masked Secrets)
    # -------------------------------------------------------------------------
    database_url: SecretString = Field(
        default=SecretString("postgresql+asyncpg://rag:rag@localhost:5432/rag"),
        description="Async connection URI for PostgreSQL",
    )
    postgres_user: str = Field(
        default="rag",
        description="PostgreSQL username",
    )
    postgres_password: str = Field(
        default="rag",
        description="PostgreSQL password",
    )
    postgres_db: str = Field(
        default="rag",
        description="PostgreSQL database name",
    )
    postgres_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
        description="PostgreSQL host port",
    )

    redis_url: SecretString = Field(
        default=SecretString("redis://localhost:6379/0"),
        description="Redis connection URI",
    )

    migration_database_url: SecretString = Field(
        default=SecretString(""),
        description="Async connection URI for PostgreSQL DDL migrations (Alembic). "
        "When empty, falls back to DATABASE_URL. In production, this should use "
        "the rag_migrator role with DDL privileges.",
    )

    # -------------------------------------------------------------------------
    # Future Capabilities (Explicitly Reserved, Never Exposed)
    # -------------------------------------------------------------------------
    llm_provider: str = Field(default="")
    llm_model: str = Field(default="")
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    gemini_api_key: SecretStr = Field(default=SecretStr(""))

    embedding_provider: str = Field(default="")
    embedding_model: str = Field(default="")
    embedding_dimensions: int = Field(
        default=1536,
        ge=1,
        le=4096,
        description="Target dimension size for dense vector embeddings",
    )

    storage_provider: str = Field(default="local")
    storage_bucket: str = Field(default="")
    storage_dir: str = Field(
        default="data/storage",
        description="Durable local directory for uploaded source documents",
    )
    max_upload_size_bytes: int = Field(
        default=26214400,  # 25 MB
        ge=1024,
        description="Maximum permitted file upload size in bytes",
    )

    jwt_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Secret key for JWT verification (Phase 1+)",
    )

    # -------------------------------------------------------------------------
    # Authentication & Password Policy (Phase 2)
    # -------------------------------------------------------------------------
    password_min_length: int = Field(
        default=8,
        ge=8,
        description="Minimum permitted user password length",
    )
    password_max_length: int = Field(
        default=128,
        le=4096,
        description="Maximum permitted user password length",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="Allowlisted HMAC algorithm for signing JWT access tokens",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        ge=1,
        description="Lifetime duration of short-lived JWT access tokens in minutes",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        description="Lifetime duration of persisted refresh tokens in days",
    )
    auth_cookie_name: str = Field(
        default="rag_refresh_token",
        description="Name of the HttpOnly refresh token cookie",
    )
    auth_cookie_secure: bool = Field(
        default=False,
        description="Enforce Secure (HTTPS) flag on auth cookies",
    )
    auth_cookie_samesite: str = Field(
        default="lax",
        description="SameSite policy for refresh token cookie (lax, strict, none)",
    )
    login_rate_limit_attempts: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=300, ge=1, le=86400)

    # -------------------------------------------------------------------------
    # Field Validators
    # -------------------------------------------------------------------------
    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_and_validate_environment(cls, v: Any) -> Environment:
        """Normalize environment strings, requiring explicit configuration."""
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError(
                "APP_ENV must be explicitly configured and non-empty (e.g. 'development', 'staging', 'production', 'testing'). "
                "Silent fallback to development is prohibited."
            )
        if isinstance(v, Environment):
            return v
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean == "test":
                return Environment.TESTING
            try:
                return Environment(clean)
            except ValueError:
                raise ValueError(
                    f"Invalid environment '{v}'. Must be one of: "
                    f"{', '.join(e.value for e in Environment)}"
                )
        raise ValueError("Environment must be a string")

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log verbosity level."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        clean = v.strip().upper() if isinstance(v, str) else ""
        if clean not in allowed:
            raise ValueError(f"Invalid log_level '{v}'. Allowed: {', '.join(allowed)}")
        return clean

    @field_validator("jwt_algorithm", mode="before")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        clean = v.strip().upper() if isinstance(v, str) else ""
        if clean not in {"HS256", "HS384", "HS512"}:
            raise ValueError("JWT_ALGORITHM must be one of HS256, HS384, HS512")
        return clean

    @field_validator("auth_cookie_samesite", mode="before")
    @classmethod
    def validate_cookie_samesite(cls, v: str) -> str:
        clean = v.strip().lower() if isinstance(v, str) else ""
        if clean not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        return clean

    @field_validator(
        "organization_logo_url",
        "organization_website_url",
        "assistant_avatar_url",
        "favicon_url",
        "logo_url",
    )
    @classmethod
    def validate_branding_url(cls, v: str, info: Any) -> str:
        """Validate optional branding URLs to ensure safe schemes."""
        if not v:
            return ""
        clean = v.strip()
        if not clean.startswith(("http://", "https://", "/")):
            raise ValueError(
                f"{info.field_name} must be an absolute URL (http://, https://) or root-relative path (/...)"
            )
        return clean

    @field_validator("primary_color", "secondary_color", "accent_color")
    @classmethod
    def validate_hex_color(cls, v: str, info: Any) -> str:
        """Validate hex color code format."""
        if not HEX_COLOR_PATTERN.match(v):
            raise ValueError(
                f"{info.field_name} must be a valid hex color code (e.g. #2563EB or #FFF)"
            )
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> SecretString:
        """Validate database URL format."""
        raw_val = v.get_secret_value() if hasattr(v, "get_secret_value") else str(v)
        valid_schemes = (
            "postgresql://",
            "postgresql+asyncpg://",
            "postgresql+psycopg://",
            "sqlite+aiosqlite://",
        )
        if not raw_val.startswith(valid_schemes):
            raise ValueError(
                "DATABASE_URL must start with a valid database driver scheme (e.g. postgresql+asyncpg://)"
            )
        return SecretString(raw_val)

    @field_validator("redis_url", mode="before")
    @classmethod
    def validate_redis_url(cls, v: Any) -> SecretString:
        """Validate redis URL format."""
        raw_val = v.get_secret_value() if hasattr(v, "get_secret_value") else str(v)
        if not raw_val.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return SecretString(raw_val)

    @field_validator("migration_database_url", mode="before")
    @classmethod
    def validate_migration_database_url(cls, v: Any) -> SecretString:
        """Validate migration database URL format (empty string allowed as fallback)."""
        raw_val = v.get_secret_value() if hasattr(v, "get_secret_value") else str(v)
        if not raw_val:
            return SecretString("")
        valid_schemes = (
            "postgresql://",
            "postgresql+asyncpg://",
            "postgresql+psycopg://",
        )
        if not raw_val.startswith(valid_schemes):
            raise ValueError(
                "MIGRATION_DATABASE_URL must start with a valid PostgreSQL driver scheme "
                "(e.g. postgresql+asyncpg://) or be empty to fall back to DATABASE_URL."
            )
        return SecretString(raw_val)

    # -------------------------------------------------------------------------
    # Model Validators (Cross-field & Production Safety)
    # -------------------------------------------------------------------------
    @model_validator(mode="after")
    def sync_backward_compatible_aliases(self) -> "Settings":
        """Synchronize aliases between Phase 0 and Phase 1 field names."""
        # Sync logo_url and organization_logo_url
        if self.organization_logo_url and not self.logo_url:
            self.logo_url = self.organization_logo_url
        elif self.logo_url and not self.organization_logo_url:
            self.organization_logo_url = self.logo_url

        # Sync bot_name and assistant_name
        if self.assistant_name != "AI Assistant" and self.bot_name == "AI Assistant":
            self.bot_name = self.assistant_name
        elif self.bot_name != "AI Assistant" and self.assistant_name == "AI Assistant":
            self.assistant_name = self.bot_name

        return self

    @model_validator(mode="before")
    @classmethod
    def set_production_defaults(cls, data: Any) -> Any:
        """Ensure security defaults are applied when running in production."""
        if isinstance(data, dict):
            env_val = data.get("app_env", "")
            if isinstance(env_val, Environment):
                env_val = env_val.value
            if str(env_val).lower() == "production":
                # If auth_cookie_secure is not explicitly supplied or is empty, default to True in production
                if "auth_cookie_secure" not in data or data.get("auth_cookie_secure") in (None, ""):
                    data["auth_cookie_secure"] = True
            else:
                if data.get("auth_cookie_secure") in (None, ""):
                    data["auth_cookie_secure"] = False
        return data

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """Enforce strict security and configuration rules in production."""
        if self.is_production:
            # 1. DEBUG must be False in production
            if self.debug:
                raise ValueError("DEBUG mode cannot be enabled in production environment.")

            # 2. Production CORS validation (fail safely if missing, empty, wildcard, or malformed)
            if not self.parsed_cors_origins:
                raise ValueError(
                    "Empty CORS_ORIGINS is not allowed in production environment. "
                    "Specify explicit trusted domains in CORS_ORIGINS (e.g. 'https://rag.example.com')."
                )

            if "*" in self.parsed_cors_origins:
                raise ValueError(
                    "Wildcard CORS ('*') is not allowed in production environment. "
                    "Specify explicit trusted domains in CORS_ORIGINS."
                )

            for origin in self.parsed_cors_origins:
                if not origin.startswith(("https://", "http://")):
                    raise ValueError(
                        f"Invalid CORS origin '{origin}'. Production CORS origins must include a valid scheme (e.g. 'https://domain.com')."
                    )
                if origin.endswith("/") and not origin.endswith("://"):
                    raise ValueError(
                        f"Invalid CORS origin '{origin}'. CORS origins must not include a trailing slash or path."
                    )

            # 3. SQLite is prohibited in production
            if self.raw_database_url.startswith("sqlite"):
                raise ValueError("SQLite database cannot be used in production environment.")

            # 4. Defensible policy for production JWT secrets
            raw_secret = self.jwt_secret.get_secret_value().strip()
            if not raw_secret:
                raise ValueError(
                    "JWT_SECRET must be configured and non-empty in production environment. "
                    "Generate a cryptographically secure key via 'openssl rand -hex 32' or 'python -c \"import secrets; print(secrets.token_hex(32))\"'."
                )
            if len(raw_secret) < 32:
                raise ValueError(
                    "JWT_SECRET must be at least 32 characters in production environment. "
                    "Generate a cryptographically secure key via 'openssl rand -hex 32' or 'python -c \"import secrets; print(secrets.token_hex(32))\"'."
                )

            # Reject trivial repetitive patterns and low character diversity (< 4 distinct characters)
            if len(set(raw_secret)) < 4:
                raise ValueError(
                    "JWT_SECRET is trivial or repetitive (insufficient distinct characters). "
                    "A cryptographically secure key is required in production (e.g. 'openssl rand -hex 32')."
                )

            # Reject repeated short cycles (e.g. "abababab..." or "123123123...")
            for cycle_len in (1, 2, 3, 4):
                cycle = raw_secret[:cycle_len]
                if cycle * (len(raw_secret) // cycle_len) == raw_secret[: cycle_len * (len(raw_secret) // cycle_len)] and len(set(raw_secret)) <= cycle_len:
                    raise ValueError(
                        "JWT_SECRET consists of a repeating pattern. "
                        "A cryptographically secure key is required in production (e.g. 'openssl rand -hex 32')."
                    )

            # Reject known weak placeholder phrases without claiming heuristics prove true randomness
            lower_secret = raw_secret.lower()
            known_placeholders = (
                "placeholder",
                "changeme",
                "defaultsecret",
                "password123",
                "secretkey123",
                "your-secret-key",
                "your-jwt-secret",
                "replace-me",
                "replace_me",
                "example-secret",
            )
            if any(p in lower_secret for p in known_placeholders):
                raise ValueError(
                    "JWT_SECRET contains a known placeholder value. "
                    "Operators must generate a unique, cryptographically secure key (e.g. 'openssl rand -hex 32')."
                )

            # 5. Enforce Secure Cookies in production (F-05)
            if not self.auth_cookie_secure:
                raise ValueError("AUTH_COOKIE_SECURE must be True in production environment.")

            # 6. Database Runtime Role Validation (F-07, F-12B)
            raw_db = self.raw_database_url.strip()
            if not raw_db:
                raise ValueError("DATABASE_URL must be configured and non-empty in production environment.")

            def _extract_db_user(url: str) -> str:
                match = re.search(r"://([^:@/]+)(?::[^@]*)?@", url)
                return match.group(1).lower() if match else ""

            def _extract_db_password(url: str) -> str:
                match = re.search(r"://[^:@/]+:([^@]+)@", url)
                return match.group(1) if match else ""

            app_user = _extract_db_user(raw_db)
            if not app_user:
                raise ValueError("DATABASE_URL must include a valid username in production environment.")

            app_pass = _extract_db_password(raw_db)
            if not app_pass:
                raise ValueError("DATABASE_URL must include a non-empty password in production environment.")

            # Reject default / placeholder database credentials in production
            weak_patterns = [
                "rag:rag@",
                "postgres:postgres@",
                "admin:admin@",
                ":password@",
                ":changeme@",
                ":rag_app_dev@",
                ":rag_migrator_dev@",
                ":rag_dev_init_pass_only@",
                ":rag_app_dev_pass_only@",
                ":rag_migrator_dev_pass_only@",
                "rag_app:rag_app_dev@",
                "rag_migrator:rag_migrator_dev@",
            ]
            raw_db_lower = raw_db.lower()
            for wp in weak_patterns:
                if wp in raw_db_lower:
                    raise ValueError(
                        f"Default or placeholder database credentials are not permitted in production: pattern '{wp}'."
                    )

            # If migration_database_url is explicitly configured, validate it
            raw_mig_explicit = self.migration_database_url.get_secret_value().strip()
            if raw_mig_explicit:
                self.validate_migration_safety()

            if "postgres_password" in self.model_fields_set and self.postgres_password.lower() in {
                "rag",
                "postgres",
                "password",
                "admin",
                "changeme",
                "rag_app_dev",
                "rag_migrator_dev",
                "rag_dev_init_pass_only",
                "rag_app_dev_pass_only",
                "rag_migrator_dev_pass_only",
            }:
                raise ValueError(
                    "POSTGRES_PASSWORD is set to an insecure default/placeholder in production."
                )

            # 7. Reject default unauthenticated Redis URL in production (F-07)
            if self.raw_redis_url in {"redis://localhost:6379/0", "redis://redis:6379/0"}:
                raise ValueError(
                    "Default unauthenticated REDIS_URL is not permitted in production environment."
                )

            # 8. Reject mock/deterministic LLM/embedding providers in production (F-11)
            if self.llm_provider.strip().lower() in {"deterministic", "mock", "test"}:
                raise ValueError(
                    "Deterministic or mock LLM_PROVIDER is not permitted in production environment."
                )

            if self.embedding_provider.strip().lower() in {"deterministic", "mock", "test"}:
                raise ValueError(
                    "Deterministic or mock EMBEDDING_PROVIDER is not permitted in production environment."
                )

            if (self.llm_provider.strip().lower() == "openai" or self.embedding_provider.strip().lower() == "openai") and not self.openai_api_key.get_secret_value().strip():
                raise ValueError(
                    "OPENAI_API_KEY must be configured and non-empty when using OpenAI providers."
                )

        return self

    def validate_migration_safety(self) -> None:
        """Validate dedicated migration credentials when executing schema migrations (F-07, F-12B).

        Enforces that:
        1. In production, MIGRATION_DATABASE_URL must be configured, non-empty, and distinct from DATABASE_URL.
        2. Fallback to runtime DATABASE_URL is strictly prohibited in production.
        3. Migration role (rag_migrator) cannot share user identity with runtime role (rag_app).
        4. Valid distinct passwords are required and default/placeholder credentials are rejected.
        """
        if not self.is_production:
            return

        raw_db = self.raw_database_url.strip()
        raw_mig_explicit = self.migration_database_url.get_secret_value().strip()

        if not raw_mig_explicit:
            raise ValueError(
                "MIGRATION_DATABASE_URL must be configured and non-empty in production environment. "
                "Fallback to DATABASE_URL is strictly prohibited in production."
            )

        if raw_mig_explicit == raw_db:
            raise ValueError(
                "DATABASE_URL and MIGRATION_DATABASE_URL cannot be identical in production environment. "
                "Distinct runtime (DML) and migration (DDL) roles are required."
            )

        def _extract_db_user(url: str) -> str:
            match = re.search(r"://([^:@/]+)(?::[^@]*)?@", url)
            return match.group(1).lower() if match else ""

        def _extract_db_password(url: str) -> str:
            match = re.search(r"://[^:@/]+:([^@]+)@", url)
            return match.group(1) if match else ""

        app_user = _extract_db_user(raw_db)
        mig_user = _extract_db_user(raw_mig_explicit)

        if not mig_user:
            raise ValueError("MIGRATION_DATABASE_URL must include a valid username in production environment.")

        if app_user and app_user == mig_user:
            raise ValueError(
                f"DATABASE_URL and MIGRATION_DATABASE_URL must not share the same user ('{app_user}') "
                "in production environment. Distinct runtime (DML) and migration (DDL) roles are required."
            )

        mig_pass = _extract_db_password(raw_mig_explicit)
        if not mig_pass:
            raise ValueError("MIGRATION_DATABASE_URL must include a non-empty password in production environment.")

        weak_patterns = [
            "rag:rag@",
            "postgres:postgres@",
            "admin:admin@",
            ":password@",
            ":changeme@",
            ":rag_app_dev@",
            ":rag_migrator_dev@",
            ":rag_dev_init_pass_only@",
            ":rag_app_dev_pass_only@",
            ":rag_migrator_dev_pass_only@",
            "rag_app:rag_app_dev@",
            "rag_migrator:rag_migrator_dev@",
        ]
        raw_mig_lower = raw_mig_explicit.lower()
        for wp in weak_patterns:
            if wp in raw_mig_lower:
                raise ValueError(
                    f"Default or placeholder migration database credentials are not permitted in production: pattern '{wp}'."
                )

    # -------------------------------------------------------------------------
    # Properties & Utilities
    # -------------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        """Return True if running in production environment."""
        return self.app_env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Return True if running in development environment."""
        return self.app_env == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        """Return True if running in test environment."""
        return self.app_env == Environment.TESTING

    @property
    def raw_database_url(self) -> str:
        """Return unmasked database URL string for internal engine binding."""
        return self.database_url.get_secret_value()

    @property
    def raw_redis_url(self) -> str:
        """Return unmasked redis URL string for internal client binding."""
        return self.redis_url.get_secret_value()

    @property
    def raw_migration_database_url(self) -> str:
        """Return unmasked migration database URL. In production, fallback is prohibited."""
        migration_url = self.migration_database_url.get_secret_value().strip()
        if not migration_url:
            if self.is_production:
                raise ValueError(
                    "MIGRATION_DATABASE_URL is required in production and cannot fall back to DATABASE_URL."
                )
            return self.raw_database_url
        return migration_url

    @property
    def parsed_cors_origins(self) -> List[str]:
        """Return CORS origins as a normalized list of strings."""
        if isinstance(self.cors_origins, list):
            return self.cors_origins
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def to_public_config(self) -> PublicConfigResponse:
        """Map server settings into safe, browser-consumable public configuration (Layer B).

        Guarantees that database credentials, Redis URLs, internal ports, and API keys
        are strictly excluded from the returned payload.
        """
        effective_logo = self.organization_logo_url or self.logo_url
        effective_bot = self.assistant_name or self.bot_name

        return PublicConfigResponse(
            application=ApplicationPublicConfig(
                name=self.app_name,
                version=self.app_version,
                environment=self.app_env.value,
            ),
            organization=OrganizationPublicConfig(
                name=self.organization_name,
                logoUrl=effective_logo,
                websiteUrl=self.organization_website_url,
            ),
            assistant=AssistantPublicConfig(
                name=effective_bot,
                description=self.assistant_description,
                avatarUrl=self.assistant_avatar_url,
            ),
            branding=BrandingPublicConfig(
                primaryColor=self.primary_color,
                secondaryColor=self.secondary_color,
                accentColor=self.accent_color,
                faviconUrl=self.favicon_url,
            ),
            features=FeaturesPublicConfig(
                chat=self.enable_chat,
                documents=self.enable_documents,
                ingestion=self.enable_ingestion,
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
