"""Alembic Environment Script.

Configured for SQLAlchemy 2.0 Async Engine:
- Dynamically loads DATABASE_URL from app.core.config.get_settings()
- Uses Base.metadata from app.db.base
- Runs async migrations via connection.run_sync
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401 - Register models for metadata discovery

config = getattr(context, "config", None)

if config is not None and config.config_file_name is not None:
    fileConfig(config.config_file_name)


def resolve_migration_url(alembic_config=None, settings_override=None) -> str:
    """Resolve and validate the database URL for Alembic migrations.

    Enforces that:
    1. Settings are loaded and production safety is validated across ALL migration paths.
    2. In production, migrations strictly require and consume MIGRATION_DATABASE_URL with
       the dedicated migration role (rag_migrator).
    3. Overriding with a custom or runtime sqlalchemy.url in production is rejected if it
       diverges from the validated MIGRATION_DATABASE_URL or shares the runtime role.
    4. In development/testing, an explicitly supplied sqlalchemy.url is honored, or defaults
       to raw_migration_database_url (with safe fallback to runtime DATABASE_URL).
    """
    cfg = alembic_config if alembic_config is not None else getattr(context, "config", None)
    settings = settings_override if settings_override is not None else get_settings()
    if settings.is_production:
        settings.validate_production_safety()
        settings.validate_migration_safety()

    configured_url = cfg.get_main_option("sqlalchemy.url") if cfg is not None else None

    if settings.is_production:
        expected_url = settings.raw_migration_database_url
        if configured_url:
            # If an explicit URL was configured, it must match the validated MIGRATION_DATABASE_URL
            if configured_url.strip() != expected_url.strip():
                raise ValueError(
                    "In production, Alembic migrations must execute using the configured MIGRATION_DATABASE_URL. "
                    "Overriding with a diverging sqlalchemy.url or runtime role is prohibited."
                )
        return expected_url
    else:
        # Development / Testing
        if configured_url and configured_url.strip():
            return configured_url.strip()
        return settings.raw_migration_database_url


# Set the validated migration URL in alembic context configuration
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = resolve_migration_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within a connection context."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using AsyncEngine."""
    migration_url = resolve_migration_url()
    configuration = config.get_section(config.config_ini_section, {}) if config else {}
    configuration["sqlalchemy.url"] = migration_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if config is not None:
    try:
        if context.is_offline_mode():
            run_migrations_offline()
        else:
            run_migrations_online()
    except (NameError, AttributeError):
        pass
