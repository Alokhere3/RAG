"""Unit tests for F-02: Docker build-context isolation and .dockerignore rules."""

from pathlib import Path
import fnmatch
import pytest


@pytest.fixture
def dockerignore_patterns():
    """Load and normalize patterns from backend/.dockerignore."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    dockerignore_path = backend_dir / ".dockerignore"
    assert dockerignore_path.exists(), "backend/.dockerignore must exist"

    patterns = []
    for line in dockerignore_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def is_ignored(rel_path: str, patterns: list[str]) -> bool:
    """Check if relative path matches any pattern in dockerignore list."""
    # Normalize path separators
    clean_path = rel_path.replace("\\", "/")
    parts = clean_path.split("/")

    for pattern in patterns:
        p = pattern.rstrip("/")
        # Check direct glob match or directory prefix match
        if fnmatch.fnmatch(clean_path, p) or fnmatch.fnmatch(clean_path, pattern):
            return True
        if fnmatch.fnmatch(parts[0], p):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, p):
                return True
    return False


def test_sensitive_artifacts_excluded_by_dockerignore(dockerignore_patterns):
    """Ensure sensitive data, local SQLite databases, uploads, and secrets are excluded."""
    sensitive_samples = [
        "dev.db",
        "custom_test.db",
        "local.sqlite",
        "sqlite.sqlite3",
        "data/storage/sample.pdf",
        "storage/artifacts/extracted.txt",
        "backups/rag_backup.tar.gz",
        ".env",
        ".env.production",
        ".env.local",
        "tests/unit/test_config.py",
        "test_pipeline_e2e.py",
        "canary_secret.txt",
        "canary_data.bin",
    ]

    for sample in sensitive_samples:
        assert is_ignored(sample, dockerignore_patterns), (
            f"F-02 VIOLATION: Sensitive or runtime path '{sample}' must be ignored by .dockerignore"
        )


def test_required_application_sources_not_excluded(dockerignore_patterns):
    """Ensure application source files and dependency manifests are NOT accidentally excluded."""
    required_samples = [
        "Dockerfile",
        "requirements.txt",
        "alembic.ini",
        "app/main.py",
        "app/core/config.py",
        "app/api/v1/router.py",
        "app/models/user.py",
        "alembic/env.py",
        "alembic/versions/0001_baseline.py",
    ]

    for sample in required_samples:
        assert not is_ignored(sample, dockerignore_patterns), (
            f"REGRESSION: Application source file '{sample}' is accidentally ignored by .dockerignore"
        )
