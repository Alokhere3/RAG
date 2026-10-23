"""Integration tests for Alembic migration commands and configuration."""

import os
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config


def test_alembic_configuration_validity():
    """Verify alembic.ini is present and configured with correct script location."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = base_dir / "alembic.ini"
    assert ini_path.exists()

    cfg = Config(str(ini_path))
    assert cfg.get_main_option("script_location") == "alembic"


def test_alembic_upgrade_and_downgrade(tmp_path: Path):
    """Test 017: Verify alembic upgrade head and downgrade -1 run cleanly."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = base_dir / "alembic.ini"

    test_db_file = tmp_path / "test_migration.db"
    test_db_url = f"sqlite+aiosqlite:///{test_db_file.as_posix()}"

    # Configure Alembic pointing to temp database
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", test_db_url)
    # Ensure sys.path includes backend
    cfg.set_main_option("prepend_sys_path", str(base_dir))

    # Test upgrade head
    command.upgrade(cfg, "head")

    # Test downgrade to base / -1
    command.downgrade(cfg, "base")
