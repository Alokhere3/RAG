"""Integration tests for Phase 2 authentication migrations and schema validation."""

from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_auth_migration_upgrade_and_downgrade(tmp_path: Path):
    """Verify 0002_auth_users creates users and refresh_tokens tables, and downgrade removes them."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = base_dir / "alembic.ini"
    assert ini_path.exists()

    test_db_file = tmp_path / "test_auth_migration.db"
    test_db_url = f"sqlite:///{test_db_file.as_posix()}"
    async_db_url = f"sqlite+aiosqlite:///{test_db_file.as_posix()}"

    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", async_db_url)
    cfg.set_main_option("prepend_sys_path", str(base_dir))

    # Step 1: Upgrade to head (applies 0001_baseline and 0002_auth_users)
    command.upgrade(cfg, "head")

    sync_engine = create_engine(test_db_url)
    inspector = inspect(sync_engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "refresh_tokens" in tables

    # Inspect users columns
    user_cols = {col["name"]: col for col in inspector.get_columns("users")}
    assert "id" in user_cols
    assert "email" in user_cols
    assert "password_hash" in user_cols
    assert "display_name" in user_cols
    assert "role" in user_cols
    assert "status" in user_cols
    assert "created_at" in user_cols
    assert "updated_at" in user_cols
    assert "last_login_at" in user_cols

    # Inspect refresh_tokens columns and foreign keys
    token_cols = {col["name"]: col for col in inspector.get_columns("refresh_tokens")}
    assert "id" in token_cols
    assert "user_id" in token_cols
    assert "token_hash" in token_cols
    assert "expires_at" in token_cols
    assert "created_at" in token_cols
    assert "revoked_at" in token_cols
    assert "replaced_by_token_id" in token_cols
    assert "user_agent" in token_cols
    assert "ip_address" in token_cols

    # Step 2: Downgrade back to baseline 0001_baseline
    command.downgrade(cfg, "0001_baseline")

    inspector_after_down = inspect(sync_engine)
    tables_after_down = inspector_after_down.get_table_names()
    assert "users" not in tables_after_down
    assert "refresh_tokens" not in tables_after_down

    # Step 3: Re-upgrade to head
    command.upgrade(cfg, "head")
    inspector_re_up = inspect(sync_engine)
    tables_re_up = inspector_re_up.get_table_names()
    assert "users" in tables_re_up
    assert "refresh_tokens" in tables_re_up

    sync_engine.dispose()
