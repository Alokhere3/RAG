"""Unit tests verifying upload limits, migration decoupling, and supply-chain CI (F-12A, F-12B, F-12C)."""

from pathlib import Path
import re

from app.core.config import get_settings


def test_nginx_client_max_body_size_matches_backend_setting():
    """Verify Nginx client_max_body_size is 25M, matching backend 25 MB max upload (F-12A)."""
    nginx_conf_path = Path(__file__).resolve().parents[3] / "deployment" / "nginx" / "nginx.conf"
    assert nginx_conf_path.exists(), f"nginx.conf not found at {nginx_conf_path}"

    content = nginx_conf_path.read_text(encoding="utf-8")
    match = re.search(r"client_max_body_size\s+([0-9]+)([kKmMgG])\s*;", content)
    assert match is not None, "client_max_body_size directive not found in nginx.conf"

    size_val = int(match.group(1))
    unit = match.group(2).upper()
    assert size_val == 25 and unit == "M", f"Expected client_max_body_size 25M, found {size_val}{unit}"

    # Verify backend setting matches (25 MB = 26,214,400 bytes)
    settings = get_settings()
    assert settings.max_upload_size_bytes == 25 * 1024 * 1024


def test_dockerfile_supports_decoupled_migrations():
    """Verify Dockerfile conditionally runs migrations and uses exec for signal handling (F-12B)."""
    dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile"
    assert dockerfile_path.exists(), f"Dockerfile not found at {dockerfile_path}"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "RUN_MIGRATIONS_ON_STARTUP" in content, "Dockerfile CMD does not reference RUN_MIGRATIONS_ON_STARTUP"
    assert "exec uvicorn" in content, "Dockerfile CMD does not use exec to forward signals to uvicorn"


def test_requirements_lock_and_ci_workflow_exist():
    """Verify supply chain reproducible lockfile and GitHub Actions CI workflow exist (F-12C)."""
    repo_root = Path(__file__).resolve().parents[3]

    lockfile = repo_root / "backend" / "requirements.lock"
    assert lockfile.exists(), f"requirements.lock not found at {lockfile}"
    assert lockfile.stat().st_size > 100, "requirements.lock is empty or truncated"

    ci_workflow = repo_root / ".github" / "workflows" / "security-ci.yml"
    assert ci_workflow.exists(), f"security-ci.yml not found at {ci_workflow}"
    assert ci_workflow.stat().st_size > 200, "security-ci.yml is empty or truncated"


def test_init_roles_sql_defines_least_privilege_roles():
    """Verify init-roles.sql defines least-privilege roles, schema ownership, and default privileges (F-12B)."""
    repo_root = Path(__file__).resolve().parents[3]
    init_roles = repo_root / "deployment" / "docker" / "postgres" / "init-roles.sql"
    assert init_roles.exists(), f"init-roles.sql not found at {init_roles}"

    content = init_roles.read_text(encoding="utf-8")
    assert "rag_migrator" in content, "init-roles.sql must define rag_migrator role"
    assert "rag_app" in content, "init-roles.sql must define rag_app role"
    assert "SELECT" in content.upper(), "init-roles.sql must grant SELECT to rag_app"
    assert "INSERT" in content.upper(), "init-roles.sql must grant INSERT to rag_app"
    assert "UPDATE" in content.upper(), "init-roles.sql must grant UPDATE to rag_app"
    assert "DELETE" in content.upper(), "init-roles.sql must grant DELETE to rag_app"

    # Schema ownership / management for migrator
    assert "OWNER TO rag_migrator" in content or "OWNER TO \"rag_migrator\"" in content, (
        "init-roles.sql must assign public schema ownership to rag_migrator"
    )

    # Future object permissions via ALTER DEFAULT PRIVILEGES FOR ROLE rag_migrator
    assert "FOR ROLE rag_migrator" in content, (
        "init-roles.sql must configure ALTER DEFAULT PRIVILEGES FOR ROLE rag_migrator so "
        "tables created during migrations grant DML to rag_app"
    )

    # Explicit revocation of DDL from rag_app
    assert "REVOKE CREATE ON SCHEMA public FROM rag_app" in content, (
        "init-roles.sql must explicitly revoke CREATE ON SCHEMA public from rag_app"
    )


def test_alembic_url_selection_prefers_migration_database_url(monkeypatch):
    """Verify Alembic consumes MIGRATION_DATABASE_URL over DATABASE_URL when present (F-12B)."""
    from alembic.config import Config
    from app.core.config import Settings

    mig_url = "postgresql+asyncpg://rag_migrator:MigratorPass123!@localhost:5432/rag"
    app_url = "postgresql+asyncpg://rag_app:AppPass456!@localhost:5432/rag"

    test_settings = Settings(
        database_url=app_url,
        migration_database_url=mig_url,
    )
    assert test_settings.raw_migration_database_url == mig_url

    # When migration_database_url is unset, falls back to database_url
    fallback_settings = Settings(
        database_url=app_url,
        migration_database_url="",
    )
    assert fallback_settings.raw_migration_database_url == app_url


def test_init_roles_sh_script_parameterizes_credentials():
    """Verify 02-init-roles.sh safely delivers environment credentials to psql without command line argument exposure."""
    repo_root = Path(__file__).resolve().parents[3]
    init_sh = repo_root / "deployment" / "docker" / "postgres" / "02-init-roles.sh"
    assert init_sh.exists(), f"02-init-roles.sh not found at {init_sh}"

    content = init_sh.read_text(encoding="utf-8")
    assert "RAG_APP_PASSWORD" in content, "02-init-roles.sh must reference RAG_APP_PASSWORD"
    assert "RAG_MIGRATOR_PASSWORD" in content, "02-init-roles.sh must reference RAG_MIGRATOR_PASSWORD"
    assert "-v app_pass=" not in content, "02-init-roles.sh must NOT pass app_pass in process arguments (argv)"
    assert "-v migrator_pass=" not in content, "02-init-roles.sh must NOT pass migrator_pass in process arguments (argv)"
    assert "psql -v ON_ERROR_STOP=1" in content, "02-init-roles.sh must invoke psql with error stopping"
    assert "set -eu" in content, "02-init-roles.sh must use strict error handling"

