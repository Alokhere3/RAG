"""Unit tests for F-03: Backup security, fail-closed behavior, and secret redaction."""

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
import pytest

# Ensure repo root is on sys.path for deployment scripts
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from deployment.scripts.backup import create_backup


def test_backup_fails_closed_when_pg_dump_missing(tmp_path, monkeypatch):
    """Ensure missing native pg_dump raises an explicit error and creates no dump or archive."""
    output_dir = tmp_path / "backups"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    canary_secret_url = "postgresql+asyncpg://canary_user:SECRET_CANARY_PASS@localhost:5432/canary_db"

    # Simulate pg_dump missing from system PATH
    monkeypatch.setattr("shutil.which", lambda _cmd: None)

    with pytest.raises(RuntimeError) as exc_info:
        create_backup(
            output_dir=output_dir,
            storage_dir=storage_dir,
            db_url=canary_secret_url,
        )

    assert "pg_dump" in str(exc_info.value)
    # Assert no backup archives were created in output_dir
    assert list(output_dir.glob("*.tar.gz")) == []
    # Assert no leftover staging directories exist
    assert list(output_dir.iterdir()) == []


def test_backup_fails_closed_when_pg_dump_fails(tmp_path, monkeypatch):
    """Ensure non-zero exit from pg_dump raises RuntimeError and cleans staging."""
    output_dir = tmp_path / "backups"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    canary_secret_url = "postgresql+asyncpg://user:secret@localhost:5432/db"

    monkeypatch.setattr("shutil.which", lambda _cmd: "/usr/bin/pg_dump")

    def mock_run(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["pg_dump"],
            stderr="pg_dump: error: connection to server failed: Connection refused",
        )

    monkeypatch.setattr("subprocess.run", mock_run)

    with pytest.raises(RuntimeError) as exc_info:
        create_backup(
            output_dir=output_dir,
            storage_dir=storage_dir,
            db_url=canary_secret_url,
        )

    assert "Database dump failed" in str(exc_info.value)
    assert list(output_dir.glob("*.tar.gz")) == []
    assert list(output_dir.iterdir()) == []


def test_synthetic_backup_contains_no_secrets(tmp_path):
    """Verify clean SQLite backup roundtrip and ensure no connection strings appear in archive."""
    output_dir = tmp_path / "backups"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True)
    (storage_dir / "sample.txt").write_text("Hello World", encoding="utf-8")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items (name) VALUES ('canary_data')")
    conn.commit()
    conn.close()

    db_url = f"sqlite:///{db_path.as_posix()}"
    archive = create_backup(
        output_dir=output_dir,
        storage_dir=storage_dir,
        db_url=db_url,
    )

    assert archive.exists()

    # Extract in inspection directory and verify contents
    inspect_dir = tmp_path / "inspect"
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(path=inspect_dir)

    manifest_file = list(inspect_dir.glob("**/manifest.json"))[0]
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["database"]["type"] == "sqlite"

    # Verify no raw db_url is written inside database.dump
    dump_file = list(inspect_dir.glob("**/database.dump"))[0]
    dump_bytes = dump_file.read_bytes()
    assert b"POSTGRESQL_BACKUP_DUMP_URL" not in dump_bytes
    assert b"sqlite:///" not in dump_bytes
