"""Unit tests verifying PostgreSQL role reconciliation and rotation script contracts (Patch A remediation)."""

from pathlib import Path


def _load_init_roles_sql() -> str:
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "deployment" / "docker" / "postgres" / "init-roles.sql"
    assert sql_path.exists(), f"init-roles.sql not found at {sql_path}"
    return sql_path.read_text(encoding="utf-8")


def _load_rotate_sql() -> str:
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "deployment" / "docker" / "postgres" / "rotate-role-passwords.sql"
    assert sql_path.exists(), f"rotate-role-passwords.sql not found at {sql_path}"
    return sql_path.read_text(encoding="utf-8")


def _load_rotate_sh() -> str:
    root = Path(__file__).resolve().parents[3]
    sh_path = root / "deployment" / "docker" / "postgres" / "rotate-role-passwords.sh"
    assert sh_path.exists(), f"rotate-role-passwords.sh not found at {sh_path}"
    return sh_path.read_text(encoding="utf-8")


def _load_init_roles_sh() -> str:
    root = Path(__file__).resolve().parents[3]
    sh_path = root / "deployment" / "docker" / "postgres" / "02-init-roles.sh"
    assert sh_path.exists(), f"02-init-roles.sh not found at {sh_path}"
    return sh_path.read_text(encoding="utf-8")


def _load_recover_sh() -> str:
    root = Path(__file__).resolve().parents[3]
    sh_path = root / "deployment" / "docker" / "postgres" / "recover-initialization.sh"
    assert sh_path.exists(), f"recover-initialization.sh not found at {sh_path}"
    return sh_path.read_text(encoding="utf-8")


def test_init_roles_reconciles_rag_app_attributes():
    """Verify init-roles.sql explicitly strips elevated attributes from rag_app."""
    sql = _load_init_roles_sql()
    assert "NOSUPERUSER" in sql
    assert "NOCREATEDB" in sql
    assert "NOCREATEROLE" in sql
    assert "NOREPLICATION" in sql
    assert "NOBYPASSRLS" in sql
    assert "NOINHERIT" in sql


def test_init_roles_loads_passwords_via_getenv_not_cmdline():
    r"""Verify init-roles.sql loads credentials via psql \getenv from environment without CLI args."""

    sql = _load_init_roles_sql()
    assert r"\getenv app_pass RAG_APP_PASSWORD" in sql
    assert r"\getenv migrator_pass RAG_MIGRATOR_PASSWORD" in sql
    assert r"\unset app_pass" in sql
    assert r"\unset migrator_pass" in sql


def test_init_roles_revokes_unintended_memberships():
    """Verify init-roles.sql revokes all role memberships from rag_app and rag_migrator using RESTRICT."""
    sql = _load_init_roles_sql()
    assert "REVOKE %I FROM rag_app RESTRICT" in sql
    assert "REVOKE %I FROM rag_migrator RESTRICT" in sql
    assert "dependent_privilege_descriptors_still_exist" in sql
    assert "pg_auth_members" in sql


def test_init_roles_transfers_materialized_view_ownership():
    """Verify init-roles.sql uses ALTER MATERIALIZED VIEW for relkind = 'm'."""
    sql = _load_init_roles_sql()
    assert "ALTER MATERIALIZED VIEW public.%I OWNER TO rag_migrator" in sql
    assert "ALTER VIEW public.%I OWNER TO rag_migrator" in sql



def test_init_roles_fails_if_rag_app_owns_objects():
    """Verify init-roles.sql refuses to proceed if rag_app owns database, schemas, tables, routines, or types."""
    sql = _load_init_roles_sql()
    assert "pg_database WHERE datname = current_database()" in sql
    assert "pg_catalog.pg_get_userbyid(c.relowner) = 'rag_app'" in sql
    assert "pg_catalog.pg_get_userbyid(p.proowner) = 'rag_app'" in sql
    assert "pg_catalog.pg_get_userbyid(t.typowner) = 'rag_app'" in sql
    assert "t.typtype IN ('c', 'e', 'd', 'r', 'm')" in sql
    assert "REASSIGN OWNED BY rag_app TO rag_migrator;" in sql


def test_init_roles_revokes_temporary_from_public():
    """Verify init-roles.sql revokes TEMPORARY on database from PUBLIC to prevent privilege inheritance."""
    sql = _load_init_roles_sql()
    assert "REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC" in sql
    assert "GRANT CONNECT, TEMPORARY ON DATABASE %I TO rag_migrator" in sql
    assert "REVOKE CREATE, TEMPORARY ON DATABASE %I FROM rag_app" in sql


def test_init_roles_does_not_unconditionally_transfer_public_schema():
    """Verify init-roles.sql safely handles PostgreSQL 16 pg_database_owner and superuser without blindly reassigning operator schemas."""
    sql = _load_init_roles_sql()
    assert "v_public_owner IN (session_user, current_user, v_db_owner, 'pg_database_owner', 'postgres')" in sql
    assert "ALTER SCHEMA public OWNER TO rag_migrator;" in sql
    assert "preserving existing operator ownership" in sql


def test_rotate_passwords_sql_reconciles_without_schema_mutations():
    """Verify rotate-role-passwords.sql updates passwords and reconciles attributes without altering schema."""
    sql = _load_rotate_sql()
    assert "ALTER ROLE rag_app WITH" in sql
    assert "ALTER ROLE rag_migrator WITH" in sql
    assert "NOSUPERUSER" in sql
    assert "NOINHERIT" in sql
    assert r"\getenv app_pass RAG_APP_PASSWORD" in sql
    assert r"\getenv migrator_pass RAG_MIGRATOR_PASSWORD" in sql
    assert "t.typtype IN ('c', 'e', 'd', 'r', 'm')" in sql
    assert "ALTER SCHEMA public OWNER TO" not in sql


def test_bootstrap_and_rotation_scripts_do_not_expose_passwords_in_argv():
    """Verify shell scripts do NOT pass passwords as -v command-line arguments to psql."""
    init_sh = _load_init_roles_sh()
    rotate_sh = _load_rotate_sh()
    recover_sh = _load_recover_sh()

    for name, sh in (("02-init-roles.sh", init_sh), ("rotate-role-passwords.sh", rotate_sh), ("recover-initialization.sh", recover_sh)):
        assert "-v app_pass=" not in sh, f"{name} must not pass password in -v command line arguments"
        assert "-v migrator_pass=" not in sh, f"{name} must not pass password in -v command line arguments"
        assert "psql -v ON_ERROR_STOP=1" in sh

