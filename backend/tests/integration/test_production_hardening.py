"""Phase 9: Production Hardening, Deployment Safety, and Backup/Restore Tests.

Covers test cases:
- P002: Missing or weak production secret fails safely.
- P003: Wildcard CORS in production is rejected.
- P004: Database and Redis ports internal-only by default in docker-compose.
- P005: Persistent volume mappings for database and uploaded storage files.
- P006, P007, P008: Backup creation, manifest validation, clean restore, and file consistency.
- P011: Secret scan ensures no real secrets committed in templates.
- P017: Private API scan ensures no unauthorized exposure.
- P018: Sensitive credentials never appear in serialized models or logs.
- P021: White-label branding updates dynamically via runtime configuration.
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import yaml
import pytest
from pydantic import ValidationError

# Ensure root workspace directory is in sys.path to access deployment scripts
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import Environment, Settings
from deployment.scripts.backup import compute_sha256, create_backup
from deployment.scripts.restore import restore_backup



def test_p002_missing_or_weak_production_secret_fails():
    """P002: Missing or weak JWT_SECRET fails validation in production mode."""
    # 1. Missing secret
    with pytest.raises(ValidationError) as exc1:
        Settings(
            app_env=Environment.PRODUCTION,
            debug=False,
            cors_origins=["https://client.corp"],
            database_url="postgresql+asyncpg://rag:pass@db:5432/rag",
            jwt_secret="",
        )
    assert "JWT_SECRET must be configured" in str(exc1.value)

    # 2. Too short secret (< 32 characters)
    with pytest.raises(ValidationError) as exc2:
        Settings(
            app_env=Environment.PRODUCTION,
            debug=False,
            cors_origins=["https://client.corp"],
            database_url="postgresql+asyncpg://rag:pass@db:5432/rag",
            jwt_secret="short-weak-key",
        )
    assert "at least 32 characters" in str(exc2.value)


def test_p003_wildcard_cors_rejected_in_production():
    """P003: Wildcard, empty, or malformed CORS in production is strictly rejected."""
    # 1. Wildcard CORS
    with pytest.raises(ValidationError) as exc1:
        Settings(
            app_env=Environment.PRODUCTION,
            debug=False,
            cors_origins=["*"],
            database_url="postgresql+asyncpg://rag:pass@db:5432/rag",
            jwt_secret="a" * 32,
        )
    assert "Wildcard CORS ('*')" in str(exc1.value)

    # 2. Empty CORS
    with pytest.raises(ValidationError) as exc2:
        Settings(
            app_env=Environment.PRODUCTION,
            debug=False,
            cors_origins=[],
            database_url="postgresql+asyncpg://rag:pass@db:5432/rag",
            jwt_secret="a" * 32,
        )
    assert "Empty CORS_ORIGINS is not allowed" in str(exc2.value)

    # 3. Missing scheme
    with pytest.raises(ValidationError) as exc3:
        Settings(
            app_env=Environment.PRODUCTION,
            debug=False,
            cors_origins=["dashboard.client.corp"],
            database_url="postgresql+asyncpg://rag:pass@db:5432/rag",
            jwt_secret="a" * 32,
        )
    assert "must include a valid scheme" in str(exc3.value)

    # 4. Trailing slash
    with pytest.raises(ValidationError) as exc4:
        Settings(
            app_env=Environment.PRODUCTION,
            debug=False,
            cors_origins=["https://dashboard.client.corp/"],
            database_url="postgresql+asyncpg://rag:pass@db:5432/rag",
            jwt_secret="a" * 32,
        )
    assert "must not include a trailing slash" in str(exc4.value)


def test_p004_p005_docker_compose_security_and_persistence():
    """P004 & P005: Database/Redis are internal or bound to localhost, and volumes are persistent."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist at repository root"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    assert "postgres" in services
    assert "redis" in services
    assert "backend" in services

    # P004: Ensure DB and Redis ports are bound to 127.0.0.1 (not 0.0.0.0 or exposed directly)
    pg_ports = services["postgres"].get("ports", [])
    for port_mapping in pg_ports:
        assert port_mapping.startswith("127.0.0.1:"), f"PostgreSQL port must be bound to 127.0.0.1: {port_mapping}"

    redis_ports = services["redis"].get("ports", [])
    for port_mapping in redis_ports:
        assert port_mapping.startswith("127.0.0.1:"), f"Redis port must be bound to 127.0.0.1: {port_mapping}"

    # P005: Persistent volumes configured
    volumes = compose.get("volumes", {})
    assert "postgres_data" in volumes, "postgres_data persistent volume must be declared"
    assert "storage_data" in volumes, "storage_data persistent volume must be declared"

    # Verify backend and worker mount storage_data
    backend_vols = services["backend"].get("volumes", [])
    assert any("storage_data:" in str(v) for v in backend_vols), "backend must mount storage_data"


def test_p006_p007_p008_backup_and_restore_consistency():
    """P006, P007, P008: Backup is created, manifest verified, clean restore succeeds, and files match."""
    with tempfile.TemporaryDirectory() as tmp_root:
        root_dir = Path(tmp_root)
        source_storage = root_dir / "source_storage"
        source_storage.mkdir()
        backup_output = root_dir / "backups"
        backup_output.mkdir()
        clean_target_storage = root_dir / "target_storage"
        clean_target_storage.mkdir()
        restore_work = root_dir / "work"
        restore_work.mkdir()

        # 1. Create a dummy test sqlite database with document metadata
        src_db_file = root_dir / "source_test.db"
        target_db_file = root_dir / "target_test.db"
        conn = sqlite3.connect(str(src_db_file))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT, checksum TEXT)")
        cursor.execute("INSERT INTO documents VALUES ('doc-1', 'annual_report.pdf', 'hash-123')")
        cursor.execute("INSERT INTO documents VALUES ('doc-2', 'specs.txt', 'hash-456')")
        conn.commit()
        conn.close()

        # 2. Create sample files in source storage
        file1 = source_storage / "doc-1.dat"
        file1.write_bytes(b"Annual Report 2026 confidential quarterly results")
        file2 = source_storage / "sub" / "doc-2.dat"
        file2.parent.mkdir(parents=True, exist_ok=True)
        file2.write_bytes(b"Platform Technical Specifications Architecture")

        file1_sha = compute_sha256(file1)
        file2_sha = compute_sha256(file2)

        # 3. Create Backup (P006)
        src_db_url = f"sqlite+aiosqlite:///{src_db_file.as_posix()}"
        tarball = create_backup(
            output_dir=backup_output,
            storage_dir=source_storage,
            db_url=src_db_url,
            app_version="0.1.0",
        )
        assert tarball.exists()
        assert tarball.name.endswith(".tar.gz")

        # 4. Restore into clean environment (P007)
        target_db_url = f"sqlite+aiosqlite:///{target_db_file.as_posix()}"
        report = restore_backup(
            archive_path=tarball,
            target_storage_dir=clean_target_storage,
            target_db_url=target_db_url,
            work_dir=restore_work,
        )

        assert report["status"] == "success"
        assert report["files_restored"] == 2

        # 5. Consistency Verification (P008)
        # Verify restored database
        tconn = sqlite3.connect(str(target_db_file))
        tcursor = tconn.cursor()
        tcursor.execute("SELECT id, filename FROM documents ORDER BY id")
        rows = tcursor.fetchall()
        tconn.close()

        assert len(rows) == 2
        assert rows[0] == ("doc-1", "annual_report.pdf")
        assert rows[1] == ("doc-2", "specs.txt")

        # Verify restored files and checksums
        restored_file1 = clean_target_storage / "doc-1.dat"
        restored_file2 = clean_target_storage / "sub" / "doc-2.dat"

        assert restored_file1.exists()
        assert restored_file2.exists()
        assert compute_sha256(restored_file1) == file1_sha
        assert compute_sha256(restored_file2) == file2_sha
        assert restored_file1.read_bytes() == file1.read_bytes()
        assert restored_file2.read_bytes() == file2.read_bytes()


def test_p011_secret_scan_no_real_secrets_in_examples():
    """P011: Secret scan ensures no real tokens or private credentials in .env.example."""
    example_path = REPO_ROOT / ".env.example"
    assert example_path.exists()
    content = example_path.read_text(encoding="utf-8")

    # Ensure no actual API keys or passwords are leaked in the template
    suspicious_patterns = [
        "sk-proj-",
        "AIzaSy",
        "ghp_",
        "xoxb-",
        "AKIA",
    ]
    for pattern in suspicious_patterns:
        assert pattern not in content, f"Committed secret detected matching {pattern}"


def test_p017_private_endpoints_require_authentication(client):
    """P017: Private API scan ensures unauthenticated requests are rejected."""
    # Documents endpoint
    res_docs = client.get("/api/v1/documents")
    assert res_docs.status_code == 401

    # Conversations endpoint
    res_convs = client.get("/api/v1/conversations")
    assert res_convs.status_code == 401

    # Admin users endpoint
    res_admin = client.get("/api/v1/admin/users")
    assert res_admin.status_code == 401


def test_p018_secret_masking_in_repr_and_diagnostics():
    """P018: Secret masking ensures passwords and tokens never appear in plain text."""
    settings = Settings(
        jwt_secret="real-super-secret-key-that-must-be-masked-12345",
        postgres_password="actual-super-secure-db-password",
        database_url="postgresql+asyncpg://rag:actual-super-secure-db-password@localhost:5432/rag",
    )

    # Serializing database_url or settings should never print the secret
    assert "actual-super-secure-db-password" not in str(settings.database_url)
    assert "**********" in str(settings.database_url)
    assert "real-super-secret-key" not in repr(settings.jwt_secret)

    # Public config representation must strictly omit database credentials and secrets
    public_config = settings.to_public_config().model_dump()
    raw_str = json.dumps(public_config)
    assert "actual-super-secure-db-password" not in raw_str
    assert "real-super-secret-key" not in raw_str


def test_p021_branding_updates_without_image_rebuild():
    """P021: White-label branding updates dynamically via settings."""
    custom_settings = Settings(
        app_name="Acme Enterprise Intelligence",
        organization_name="Acme Corporation",
        primary_color="#10B981",
        assistant_name="Acme Genie",
        assistant_description="Internal corporate search",
    )
    public_config = custom_settings.to_public_config()
    assert public_config.application.name == "Acme Enterprise Intelligence"
    assert public_config.organization.name == "Acme Corporation"
    assert public_config.branding.primary_color == "#10B981"
    assert public_config.assistant.name == "Acme Genie"
