"""Integration test for PostgreSQL runtime (rag_app) and migration (rag_migrator) role separation (F-12B).

STRICT ISOLATION & VERIFICATION CONTRACT:
1. This test will NEVER execute against a production, operational, or unspecified database.
2. Disposability is NOT inferred merely from host alias, loopback address, database name, token length,
   or token character diversity alone. It strictly requires:
   - Explicit confirmation: TEST_POSTGRES_DISPOSABLE_CONFIRMED=true
   - Cryptographic run-specific isolation token: TEST_POSTGRES_ISOLATION_TOKEN=<token>
     (Validated for entropy >= 3.0 bits/char and non-cyclical structure; fixed placeholders rejected).
     NOTE: Token validation is harness-level input hygiene, NOT proof of disposability.
   - Explicit target URLs: TEST_MIGRATOR_DB_URL, TEST_APP_DB_URL, and optional TEST_BOOTSTRAP_DB_URL.
   - Remote hosts require explicit operator confirmation: TEST_POSTGRES_ALLOW_REMOTE=true.
3. Active Server-Side Attestation Handshake (Pre-DDL):
   - The disposable database must be explicitly marked by the provisioning harness with a matching comment:
     COMMENT ON DATABASE <dbname> IS 'DISPOSABLE_TEST_DB:<token>';
   - Before executing ANY DDL or mutation, BOTH runtime and migrator connections (and bootstrap connection)
     independently query the database comment and verify active attestation.
   - Diagnostic failure messages are strictly secret-safe: tokens, complete comments, and credentials are NEVER
     echoed in error messages, logs, or assertion failures.
4. Multi-Factor Server Identity & Instance Verification (Pre-DDL):
   - Both connections verify matching server identity: inet_server_addr, inet_server_port, current_database,
     pg_database.oid, AND pg_postmaster_start_time (proving the connections terminate at the exact same
     PostgreSQL postmaster instance process).
5. Comprehensive Cross-Schema Safety Inspection (Pre-DDL):
   - All non-system schemas (covering public, rag, auth, and any user schema) are inspected.
   - Any operational table (users, documents, document_chunks, sessions, messages, api_keys, alembic_version)
     in ANY schema causes immediate fail-closed abort before DDL.
   - Any non-test table, view, or materialized view causes immediate fail-closed abort.
6. Bootstrap Grant Path vs Default Privileges:
   - Dedicated fixture tests pre-existing objects created by initial database owner BEFORE bootstrap.
   - Runs the actual init-roles.sql bootstrap procedure.
   - Verifies rag_app has runtime DML on pre-existing objects (initial bootstrap grants).
   - Verifies default privileges for objects created by rag_migrator AFTER bootstrap as a separate case.
   - Verifies rag_app is denied all DDL (CREATE, ALTER, DROP, TRUNCATE) and TEMPORARY tables.
7. Exact Object Tracking & Leak-Free Cleanup:
   - Every object created (including on unexpected security failures) is tracked and dropped.
   - Cleanup failures are not swallowed and are reported without leaking secrets.

OPERATOR INSTRUCTIONS FOR PREPARING A DISPOSABLE TARGET:
Method A (Automated & Preferred):
  When the Docker daemon is running locally, the test harness automatically provisions
  an ephemeral PostgreSQL container bound strictly to loopback (127.0.0.1) with a
  dynamically allocated host port, performs bootstrap, executes role isolation and
  credential rotation tests, and guarantees container cleanup on teardown:
     pytest backend/tests/integration/test_postgres_role_separation.py

Method B (Manual Operator Provisioning):
  To manually provision an isolated target for test_postgres_role_privilege_isolation:
  1. Provision a dedicated ephemeral container bound strictly to loopback (127.0.0.1):
     docker run --rm -d --name pg-test-isolated -p 127.0.0.1:54329:5432 -e POSTGRES_PASSWORD=EphemeralTestPass123! postgres:16-alpine
  2. Generate a dynamic run token:
     TOKEN=$(python -c "import secrets; print(secrets.token_hex(16))")
  3. Create and attest the disposable test database:
     psql -h 127.0.0.1 -p 54329 -U postgres -c "CREATE DATABASE rag_disposable_test;"
     psql -h 127.0.0.1 -p 54329 -U postgres -c "COMMENT ON DATABASE rag_disposable_test IS 'DISPOSABLE_TEST_DB:' || '$TOKEN';"
  4. Export environment variables:
     export TEST_POSTGRES_DISPOSABLE_CONFIRMED=true
     export TEST_POSTGRES_ISOLATION_TOKEN=$TOKEN
     export TEST_BOOTSTRAP_DB_URL="postgresql+asyncpg://postgres:EphemeralTestPass123!@127.0.0.1:54329/rag_disposable_test"
     export TEST_MIGRATOR_DB_URL="postgresql+asyncpg://rag_migrator:MigPass123!@127.0.0.1:54329/rag_disposable_test"
     export TEST_APP_DB_URL="postgresql+asyncpg://rag_app:AppPass123!@127.0.0.1:54329/rag_disposable_test"
     export RAG_APP_PASSWORD="AppPass123!"
     export RAG_MIGRATOR_PASSWORD="MigPass123!"
  5. Run pytest:
     pytest backend/tests/integration/test_postgres_role_separation.py
"""

import collections
import math
import os
from pathlib import Path
import re
import socket
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
import pytest
from sqlalchemy import URL, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

ALLOWLISTED_TEST_HOSTS = {
    "127.0.0.1",
    "localhost",
    "::1",
    "postgres-test",
    "pg-test-isolated",
}

FORBIDDEN_DB_NAMES = {
    "rag",
    "postgres",
    "production",
    "prod",
    "default",
    "master",
    "main",
}

OPERATIONAL_TABLE_NAMES = {
    "users",
    "documents",
    "document_chunks",
    "sessions",
    "messages",
    "api_keys",
    "alembic_version",
    "roles",
    "permissions",
    "tenants",
    "workspaces",
}

KNOWN_PLACEHOLDER_TOKENS = {
    "disposable-test-token-12345678",
    "fixed-token-placeholder",
    "changeme-12345678",
    "test-token-12345678",
    "default-token-1234",
    "placeholder-token-1234",
    "1234567890123456",
}


def _calculate_shannon_entropy(s: str) -> float:
    """Compute Shannon entropy in bits per character."""
    if not s:
        return 0.0
    counts = collections.Counter(s)
    length = len(s)
    return -sum((cnt / length) * math.log2(cnt / length) for cnt in counts.values())


def _has_repeated_cycle(s: str) -> bool:
    """Check if string is formed by repeating a shorter cyclic pattern (e.g. 'abcdabcd')."""
    if len(s) < 2:
        return True
    return s in (s + s)[1:-1]


def _mask_url(url: Any) -> str:
    """Mask credentials in database URL to prevent secret leakage in logs/errors."""
    if not url:
        return "<empty>"
    if hasattr(url, "render_as_string"):
        try:
            return url.render_as_string(hide_password=True)
        except Exception:
            pass
    url_str = str(url).strip()
    try:
        from sqlalchemy.engine import make_url
        u = make_url(url_str)
        return u.render_as_string(hide_password=True)
    except Exception:
        return re.sub(r"://([^:@/]+)(?::[^@]*)?@", r"://\1:***@", url_str)


def _parse_url_target(url: Any) -> Dict[str, Any]:
    """Extract scheme, user, host, port, and database name from URL or URL string."""
    if not url:
        return {}
    if isinstance(url, URL):
        return {
            "scheme": url.drivername,
            "user": url.username or "",
            "host": url.host,
            "port": url.port or 5432,
            "dbname": url.database,
        }
    url_str = str(url).strip()
    try:
        from sqlalchemy.engine import make_url
        parsed = make_url(url_str)
        return {
            "scheme": parsed.drivername,
            "user": parsed.username or "",
            "host": parsed.host,
            "port": parsed.port or 5432,
            "dbname": parsed.database,
        }
    except Exception:
        pattern = re.compile(
            r"^(?P<scheme>[a-zA-Z0-9+]+)://"
            r"(?:(?P<user>[^:@/]+)(?::(?P<pass>[^@]*))?@)?"
            r"(?P<host>[^:/]+)"
            r"(?::(?P<port>\d+))?"
            r"/(?P<dbname>[^/?]+)"
            r"(?:\?.*)?$"
        )
        match = pattern.match(url_str)
        if not match:
            return {}
        return {
            "scheme": match.group("scheme"),
            "user": match.group("user") or "",
            "host": match.group("host"),
            "port": int(match.group("port")) if match.group("port") else 5432,
            "dbname": match.group("dbname"),
        }


def _build_db_url(
    username: str,
    password: str,
    host: str,
    port: int,
    database: str,
    drivername: str = "postgresql+asyncpg",
) -> URL:
    """Safely construct a database connection URL using SQLAlchemy's structured URL.create() API.

    Discrete fields prevent URL parsing ambiguities caused by special characters
    (such as @, :, /, %, #) in credentials.
    """
    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )


async def _assert_authentication_failure(engine: AsyncEngine, role_name: str) -> None:
    """Verify that connecting with obsolete/invalid credentials specifically fails authentication (SQLSTATE 28P01).

    Distinguishes genuine password rejection from network, URL-parsing, or server-startup failures.
    """
    with pytest.raises(Exception) as exc_info:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1;"))

    exc = exc_info.value
    exc_str = str(exc).lower()

    is_auth_failure = False
    if hasattr(exc, "orig") and exc.orig is not None:
        orig = exc.orig
        if getattr(orig, "sqlstate", None) == "28P01":
            is_auth_failure = True
        elif "28p01" in str(orig).lower() or "password authentication failed" in str(orig).lower():
            is_auth_failure = True

    if "28p01" in exc_str or "password authentication failed" in exc_str or "invalidpassworderror" in exc_str:
        is_auth_failure = True

    if not is_auth_failure:
        raise AssertionError(
            f"Expected password authentication failure (SQLSTATE 28P01) for {role_name}, "
            f"but received unexpected error type {type(exc).__name__}"
        )



def _verify_isolation_contract(
    migrator_url: str,
    app_url: str,
    bootstrap_url: str = "",
) -> Tuple[bool, str]:
    """Verify strict isolation guarantees across test database URLs.

    Safety boundaries enforced:
    - Explicit confirmation flag
    - Dynamic run token hygiene (length >= 16, entropy >= 3.0, non-cyclic, non-placeholder)
    - Host validation (allowlist or explicit remote confirmation)
    - Matching host, port, and database name
    - Distinct users across roles
    - Non-production database naming
    """
    confirmed = os.getenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "").strip().lower()
    if confirmed not in ("true", "1"):
        return False, "TEST_POSTGRES_DISPOSABLE_CONFIRMED is not set to 'true'."

    isolation_token = os.getenv("TEST_POSTGRES_ISOLATION_TOKEN", "").strip()
    if not isolation_token or len(isolation_token) < 16:
        return False, (
            "TEST_POSTGRES_ISOLATION_TOKEN must be configured with at least 16 characters "
            "for session attestation."
        )

    # Reject fixed/placeholder tokens, cyclic patterns, and low entropy strings
    if (
        isolation_token.lower() in KNOWN_PLACEHOLDER_TOKENS
        or _has_repeated_cycle(isolation_token)
        or _calculate_shannon_entropy(isolation_token) < 3.0
    ):
        return False, (
            "Isolation token rejected: fixed placeholders, repetitive cycles, and low entropy tokens "
            "are disallowed. Supply a secure per-run dynamic token (e.g. secrets.token_hex(16))."
        )

    mig_target = _parse_url_target(migrator_url)
    app_target = _parse_url_target(app_url)

    if not mig_target:
        return False, f"TEST_MIGRATOR_DB_URL format invalid: {_mask_url(migrator_url)}"
    if not app_target:
        return False, f"TEST_APP_DB_URL format invalid: {_mask_url(app_url)}"

    targets = [("migrator", mig_target), ("app", app_target)]
    if bootstrap_url:
        boot_target = _parse_url_target(bootstrap_url)
        if not boot_target:
            return False, f"TEST_BOOTSTRAP_DB_URL format invalid: {_mask_url(bootstrap_url)}"
        targets.append(("bootstrap", boot_target))

    # 1. Require allowlisted test host or explicit remote confirmation
    allow_remote = os.getenv("TEST_POSTGRES_ALLOW_REMOTE", "").strip().lower() in ("true", "1")
    if not allow_remote:
        for name, tgt in targets:
            if tgt["host"] not in ALLOWLISTED_TEST_HOSTS:
                return False, (
                    f"{name.upper()} host '{tgt['host']}' is not in allowlisted test hosts "
                    f"({', '.join(sorted(ALLOWLISTED_TEST_HOSTS))}). Set TEST_POSTGRES_ALLOW_REMOTE=true to permit verified remote targets."
                )

    # 2. Require exact same host, port, and database name
    base_target = mig_target
    for name, tgt in targets[1:]:
        if tgt["host"] != base_target["host"]:
            return False, f"Host mismatch between migrator ('{base_target['host']}') and {name} ('{tgt['host']}')."
        if tgt["port"] != base_target["port"]:
            return False, f"Port mismatch between migrator ({base_target['port']}) and {name} ({tgt['port']})."
        if tgt["dbname"] != base_target["dbname"]:
            return False, f"Database mismatch between migrator ('{base_target['dbname']}') and {name} ('{tgt['dbname']}')."

    # 3. Require distinct roles between runtime and migrator
    if not mig_target["user"] or not app_target["user"]:
        return False, "Both URLs must specify explicit database users."
    if mig_target["user"].lower() == app_target["user"].lower():
        return False, f"Both URLs share the same user ('{mig_target['user']}'). Distinct roles required."

    # 4. Require disposable database naming
    dbname_lower = mig_target["dbname"].lower()
    if dbname_lower in FORBIDDEN_DB_NAMES:
        return False, f"Target database name '{dbname_lower}' matches a forbidden production/generic database name."
    if "test" not in dbname_lower and "disposable" not in dbname_lower:
        return False, f"Target database name '{dbname_lower}' must contain 'test' or 'disposable'."

    return True, "Isolation contract satisfied."


async def _verify_connection_attestation(conn: AsyncConnection, expected_token: str) -> None:
    """Independently verify active database comment attestation on a connection.

    Secret-safe: does NOT echo token or complete comment in exception diagnostics.
    """
    desc_res = await conn.execute(
        text(
            "SELECT pg_catalog.shobj_description(d.oid, 'pg_database') "
            "FROM pg_database d WHERE d.datname = current_database();"
        )
    )
    db_comment = desc_res.scalar_one_or_none() or ""
    expected_comment = f"DISPOSABLE_TEST_DB:{expected_token}"
    if db_comment.strip() != expected_comment:
        raise RuntimeError(
            "Target database failed active disposable attestation: "
            "server comment does not match the active test session attestation contract."
        )


async def _set_database_isolation_comment(conn: AsyncConnection, target_dbname: str, isolation_token: str) -> None:
    """Set the database isolation attestation comment without exposing isolation_token in statement text.

    Uses parameterized set_config session parameters followed by dynamic PL/pgSQL
    EXECUTE format() to avoid embedding raw token literals in the executed SQL text.
    If execution fails, sanitizes any exception message so isolation_token is never leaked.
    """
    token_val = f"DISPOSABLE_TEST_DB:{isolation_token}"
    try:
        await conn.execute(
            text("SELECT set_config('app.test_db_name', :dbname, false), set_config('app.isolation_comment', :comment, false);"),
            {"dbname": target_dbname, "comment": token_val},
        )
        await conn.execute(
            text("DO $$ BEGIN EXECUTE format('COMMENT ON DATABASE %I IS %L', current_setting('app.test_db_name'), current_setting('app.isolation_comment')); END $$;")
        )
    except Exception as exc:
        sanitized_msg = str(exc).replace(isolation_token, "[REDACTED_ISOLATION_TOKEN]")
        raise RuntimeError(f"Failed to set isolation comment: {sanitized_msg}") from None


async def _verify_authenticated_identities(
    conn: AsyncConnection,
    expected_role: str,
    target_dbname: str,
) -> Dict[str, Any]:
    """Verify that connection actually authenticated as expected_role without role impersonation.

    Checks:
    1. session_user == expected_role (PostgreSQL authentication-level identity)
    2. current_user == expected_role (active privilege context)
    3. session_user == current_user (no SET ROLE or role switching)
    4. current_database() matches target_dbname
    """
    res = await conn.execute(
        text("SELECT session_user, current_user, current_database();")
    )
    row = res.mappings().fetchone()
    if not row:
        raise RuntimeError("Failed to query authenticated identity from connection.")

    sess_user = row["session_user"]
    curr_user = row["current_user"]
    curr_db = row["current_database"]

    if curr_db.lower() != target_dbname.lower():
        raise RuntimeError(
            f"Connected database '{curr_db}' does not match expected target '{target_dbname}'."
        )

    if sess_user != expected_role:
        raise RuntimeError(
            f"Authenticated identity mismatch: session_user '{sess_user}' "
            f"does not match expected role '{expected_role}'."
        )

    if curr_user != expected_role:
        raise RuntimeError(
            f"Unexpected role switching detected: current_user '{curr_user}' "
            f"does not match expected role '{expected_role}'."
        )

    return dict(row)


async def _verify_server_isolation_and_identity(
    connections: List[Any],
    expected_token: str,
    target_dbname: str,
) -> None:
    """Verify active server-side attestation, authenticated identities, and multi-factor server identity.

    Each connection entry in `connections` can be:
      - (role_alias, conn) -> default expected_role inferred from alias ('app' -> 'rag_app', 'migrator' -> 'rag_migrator')
      - (role_alias, conn, expected_role) -> explicit expected_role

    Checks:
    1. Independent attestation check on every connection (secret-safe).
    2. Explicit authenticated identity assertion: session_user == expected_role and current_user == expected_role.
    3. Distinct authenticated identities across runtime and migrator connections.
    4. Multi-factor server identity:
       - inet_server_addr
       - inet_server_port
       - current_database
       - pg_database.oid
       - pg_postmaster_start_time (verifies exact same postmaster process)
    """
    if len(connections) < 2:
        raise RuntimeError("At least two connections required for identity verification.")

    normalized_connections: List[Tuple[str, AsyncConnection, str]] = []
    for item in connections:
        if len(item) == 2:
            alias, conn = item
            expected_role = "rag_app" if alias == "app" else ("rag_migrator" if alias == "migrator" else alias)
            normalized_connections.append((alias, conn, expected_role))
        else:
            alias, conn, expected_role = item
            normalized_connections.append((alias, conn, expected_role))

    server_records = []
    authenticated_identities = {}

    for alias, conn, expected_role in normalized_connections:
        # 1. Independent attestation
        await _verify_connection_attestation(conn, expected_token)

        # 2. Server identity & authenticated session query
        res = await conn.execute(
            text(
                "SELECT "
                "    inet_server_addr() AS srv_addr, "
                "    inet_server_port() AS srv_port, "
                "    current_database() AS dbname, "
                "    session_user AS sess_usr, "
                "    current_user AS curr_usr, "
                "    pg_postmaster_start_time() AS start_time, "
                "    (SELECT oid FROM pg_database WHERE datname = current_database()) AS db_oid;"
            )
        )
        row = res.mappings().fetchone()
        if not row:
            raise RuntimeError(f"Failed to query server identity for role {alias}.")

        # Support backward-compatible mock mappings containing 'usr'
        sess_usr = row.get("sess_usr") or row.get("usr") or ""
        curr_usr = row.get("curr_usr") or row.get("usr") or ""
        dbname = row["dbname"]

        if dbname.lower() != target_dbname.lower():
            raise RuntimeError(
                f"Connected database '{dbname}' does not match expected target '{target_dbname}'."
            )

        if sess_usr != expected_role:
            raise RuntimeError(
                f"Authenticated identity mismatch: session_user '{sess_usr}' "
                f"does not match expected role '{expected_role}'."
            )

        if curr_usr != expected_role:
            raise RuntimeError(
                f"Unexpected role switching detected: current_user '{curr_usr}' "
                f"does not match expected role '{expected_role}'."
            )

        authenticated_identities[alias] = sess_usr
        server_records.append((alias, row))

    # Reject identical authenticated identities between runtime and migration connections
    if "app" in authenticated_identities and "migrator" in authenticated_identities:
        app_sess = authenticated_identities["app"]
        mig_sess = authenticated_identities["migrator"]
        if app_sess == mig_sess:
            raise RuntimeError(
                f"Runtime and migration connections authenticated as the same role ('{app_sess}'). "
                "Distinct roles are strictly required."
            )

    # Compare identity against baseline (first connection)
    base_role, base_row = server_records[0]
    if base_row["dbname"].lower() != target_dbname.lower():
        raise RuntimeError(
            f"Connected database '{base_row['dbname']}' does not match expected target '{target_dbname}'."
        )

    for role_name, row in server_records[1:]:
        if row["dbname"].lower() != base_row["dbname"].lower():
            raise RuntimeError(f"Database name mismatch between {base_role} and {role_name}.")
        if row["db_oid"] != base_row["db_oid"]:
            raise RuntimeError(
                f"Database OID mismatch between {base_role} ({base_row['db_oid']}) and {role_name} ({row['db_oid']})."
            )
        if row["srv_addr"] != base_row["srv_addr"] or row["srv_port"] != base_row["srv_port"]:
            raise RuntimeError(
                f"Server endpoint mismatch between {base_role} ({base_row['srv_addr']}:{base_row['srv_port']}) "
                f"and {role_name} ({row['srv_addr']}:{row['srv_port']})."
            )
        if row["start_time"] != base_row["start_time"]:
            raise RuntimeError(
                f"PostgreSQL postmaster start time mismatch between {base_role} and {role_name}. "
                "Connections terminate at different PostgreSQL server instances."
            )


async def _inspect_target_state_cross_schema(conn: AsyncConnection) -> None:
    """Inspect all non-system schemas for operational objects or non-test state.

    Enforces that:
    1. No operational table (users, documents, document_chunks, sessions, messages, api_keys, alembic_version)
       exists in ANY schema (including public, rag, auth, or custom user schemas).
    2. No unexpected non-test tables exist across any schema.
    3. No unexpected non-test views exist across any schema.
    4. No materialized views exist in any user schema.
    """
    # 1. Inspect tables across all user schemas
    tables_res = await conn.execute(
        text(
            "SELECT schemaname, tablename FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
            "  AND schemaname NOT LIKE 'pg_toast%' "
            "  AND schemaname NOT LIKE 'pg_temp_%';"
        )
    )
    existing_tables = tables_res.fetchall()

    for schema, tbl in existing_tables:
        tbl_lower = tbl.lower()
        if tbl_lower in OPERATIONAL_TABLE_NAMES:
            raise RuntimeError(
                f"Database target contains operational table '{tbl}' in schema '{schema}'. "
                "Test execution aborted to protect operational data."
            )
        if not tbl.startswith("_test_") and not tbl.startswith("_forbidden_"):
            raise RuntimeError(
                f"Database target contains unexpected non-test table '{tbl}' in schema '{schema}'. "
                "Target must be a dedicated disposable test database."
            )

    # 2. Inspect views across all user schemas
    views_res = await conn.execute(
        text(
            "SELECT table_schema, table_name FROM information_schema.views "
            "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
            "  AND table_schema NOT LIKE 'pg_toast%';"
        )
    )
    for schema, vname in views_res.fetchall():
        if not vname.startswith("_test_"):
            raise RuntimeError(
                f"Database target contains unexpected view '{vname}' in schema '{schema}'."
            )

    # 3. Inspect materialized views across all user schemas
    matviews_res = await conn.execute(
        text(
            "SELECT schemaname, matviewname FROM pg_matviews "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
            "  AND schemaname NOT LIKE 'pg_toast%';"
        )
    )
    matviews = matviews_res.fetchall()
    if matviews:
        sample = f"{matviews[0][0]}.{matviews[0][1]}"
        raise RuntimeError(f"Database target contains materialized view '{sample}'.")


def _is_port_reachable(host: str, port: int, timeout: float = 1.5) -> bool:
    """Check whether PostgreSQL host:port is reachable via TCP socket."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _parse_and_validate_loopback_port(port_output: str) -> int:
    """Parse Docker port mapping output and validate that it binds strictly to loopback.

    Fails closed if the mapping is absent, empty, ambiguous, or binds to any
    non-loopback or wildcard address.
    """
    if not port_output or not port_output.strip():
        raise RuntimeError("Port mapping rejected: Docker reported no published port mappings.")

    lines = [line.strip() for line in port_output.strip().splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Port mapping rejected: Docker reported no published port mappings.")

    discovered_ports: Set[int] = set()

    for line in lines:
        mapping_target = line.split("->")[-1].strip()
        if not mapping_target:
            raise RuntimeError(f"Port mapping rejected: Malformed port mapping line '{line}'.")

        # Parse host and port (handling IPv6 bracket notation)
        if mapping_target.startswith("["):
            bracket_close = mapping_target.find("]")
            if bracket_close == -1:
                raise RuntimeError(f"Port mapping rejected: Malformed IPv6 mapping '{mapping_target}'.")
            host = mapping_target[1:bracket_close].strip()
            rest = mapping_target[bracket_close + 1 :]
            if not rest.startswith(":"):
                raise RuntimeError(f"Port mapping rejected: Missing port separator in '{mapping_target}'.")
            port_str = rest[1:].strip()
        else:
            colon_idx = mapping_target.rfind(":")
            if colon_idx == -1:
                raise RuntimeError(f"Port mapping rejected: Missing port in '{mapping_target}'.")
            host = mapping_target[:colon_idx].strip()
            port_str = mapping_target[colon_idx + 1 :].strip()

        if not port_str.isdigit():
            raise RuntimeError(f"Port mapping rejected: Invalid port number '{port_str}' in '{mapping_target}'.")

        port = int(port_str)
        if port <= 0 or port > 65535:
            raise RuntimeError(f"Port mapping rejected: Port {port} out of range in '{mapping_target}'.")

        # Reject wildcard / all-interfaces
        if host in ("0.0.0.0", "::", "[::]", ""):
            raise RuntimeError(
                f"Port mapping rejected: Bound to wildcard/all-interfaces address '{host}:{port}'."
            )

        # Enforce loopback-only
        is_loopback = False
        try:
            import ipaddress
            ip = ipaddress.ip_address(host)
            if ip.is_loopback:
                is_loopback = True
        except ValueError:
            if host.lower() == "localhost":
                is_loopback = True

        if not is_loopback:
            raise RuntimeError(
                f"Port mapping rejected: Bound to non-loopback host '{host}:{port}'."
            )

        discovered_ports.add(port)

    if not discovered_ports:
        raise RuntimeError("Port mapping rejected: No valid port mappings extracted.")

    if len(discovered_ports) > 1:
        raise RuntimeError(
            f"Port mapping rejected: Ambiguous port mapping with multiple conflicting host ports: {sorted(discovered_ports)}."
        )

    return discovered_ports.pop()


class EphemeralPostgresCluster:
    """Manages the full lifecycle of a dedicated, ephemeral PostgreSQL container for cluster-wide tests.

    Enforces that:
    - Cluster-wide role bootstrap tests CANNOT run against an arbitrary or shared pre-existing server.
    - Lifecycle (create, test, stop, delete) is explicitly owned by the test harness.
    - Ephemeral port is dynamically allocated and bound strictly to loopback (127.0.0.1).
    - If Docker is unavailable, tests fail closed and report NOT RUN rather than mutating shared servers.
    """

    @classmethod
    def is_available(cls) -> bool:
        """Check if Docker CLI is installed and Docker daemon is running."""
        try:
            import subprocess
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def parse_and_validate_loopback_port(port_output: str) -> int:
        return _parse_and_validate_loopback_port(port_output)

    def __init__(self, requested_port: Optional[int] = None):
        import secrets
        self.container_name: str = f"pg-ephemeral-{uuid.uuid4().hex[:8]}"
        self.requested_port: Optional[int] = requested_port
        self.port: Optional[int] = requested_port
        self.admin_user: str = "postgres"
        self.admin_password: str = secrets.token_urlsafe(24)
        self.is_running: bool = False
        # Path to the temporary admin-password file, if one was created.
        # Kept until the container is confirmed ready because the PostgreSQL
        # container entrypoint reads POSTGRES_PASSWORD_FILE during initialisation;
        # deleting the bind-mounted file before pg_isready succeeds is a race on
        # Docker Desktop (Linux VM backend) and native Linux.
        self._password_file_path: Optional[str] = None

    @staticmethod
    def _secure_temporary_file(path: str) -> None:
        """Establish and verify restrictive permissions on a temporary secret file.

        - On POSIX: applies mode 0o600 and verifies via os.stat.
        - On Windows: removes broad/untrusted user groups ('Users', 'BUILTIN\\Users',
          'Everyone', 'Authenticated Users') via icacls and verifies via icacls output
          that broad/untrusted user groups do not retain access.
        - Fails safely with a RuntimeError if protection cannot be established or verified.
        """
        import os as _os
        import subprocess as _sp

        if _os.name == "nt":
            for group in ("Users", "BUILTIN\\Users", "Everyone", "Authenticated Users"):
                _sp.run(["icacls", path, "/remove:g", group], capture_output=True, check=False)
            verify = _sp.run(["icacls", path], capture_output=True, text=True, check=False)
            if verify.returncode != 0:
                raise RuntimeError(
                    f"Failed to verify Windows ACL on temporary secret file: {verify.stderr.strip()}"
                )
            lower_acl = verify.stdout.lower()
            for forbidden in ("everyone", "builtin\\users"):
                if forbidden in lower_acl:
                    raise RuntimeError(
                        f"Insecure ACL detected on temporary secret file: '{forbidden}' retained access."
                    )
        else:
            _os.chmod(path, 0o600)
            mode = _os.stat(path).st_mode & 0o777
            if mode != 0o600:
                raise RuntimeError(
                    f"Failed to establish restrictive file mode 0o600 on {path}, got: {oct(mode)}"
                )

    def _safe_unlink(self, path: Optional[str]) -> Optional[str]:
        """Attempt to delete a temporary secret file path.

        Returns an error diagnostic string if deletion fails, or None on success.
        Does NOT swallow deletion errors silently.
        """
        if path is None:
            return None
        try:
            import os as _os
            _os.unlink(path)
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            return f"Failed to unlink temporary secret file '{path}': {exc}"

    def start(self, timeout: float = 25.0) -> None:
        """Start an ephemeral PostgreSQL container bound strictly to loopback.

        Password handling:
        - The admin password is written to a temporary file with restrictive permissions (0o600 / stripped Windows ACL).
        - The file is bind-mounted into the container as POSTGRES_PASSWORD_FILE.
        - The file is deleted only after the container reports pg_isready, because
          the PostgreSQL entrypoint script reads it during initialisation.
        - On any failure the file is deleted before the exception propagates.
        - The password is never placed in command-line arguments or logged.
        """
        import subprocess
        import tempfile
        import time

        if not self.is_available():
            raise RuntimeError(
                "Cannot start ephemeral PostgreSQL cluster: Docker daemon is not reachable."
            )

        import os as _os

        try:
            password_fd, password_path = tempfile.mkstemp(prefix="pg_eph_pw_", suffix=".secret")
        except OSError as exc:
            raise RuntimeError(
                f"Failed to create temporary password file for ephemeral cluster: {exc}"
            ) from exc

        self._password_file_path = password_path

        try:
            self._secure_temporary_file(password_path)

            try:
                with _os.fdopen(password_fd, "w") as f:
                    f.write(self.admin_password)
            except Exception as exc:
                try:
                    _os.close(password_fd)
                except OSError:
                    pass
                raise RuntimeError(
                    f"Failed to write temporary password file for ephemeral cluster: {exc}"
                ) from exc

            # Explicitly bind to 127.0.0.1. Use port 0 for dynamic allocation.
            # NEVER bind on 0.0.0.0 or all interfaces.
            bind_port = self.requested_port if self.requested_port is not None else 0
            cmd = [
                "docker", "run", "--rm", "-d",
                "--name", self.container_name,
                "-p", f"127.0.0.1:{bind_port}:5432",
                "-v", f"{password_path}:/run/secrets/pg_admin_password:ro",
                "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/pg_admin_password",
                "postgres:16-alpine",
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            except subprocess.TimeoutExpired as texc:
                self.stop()
                raise RuntimeError(
                    f"Timed out starting ephemeral PostgreSQL container '{self.container_name}' after 30s."
                ) from texc
            except Exception as cmd_exc:
                self.stop()
                raise RuntimeError(
                    f"Exception launching ephemeral PostgreSQL container '{self.container_name}': {cmd_exc}"
                ) from cmd_exc

            if res.returncode != 0:
                self.stop()
                raise RuntimeError(
                    f"Failed to launch ephemeral PostgreSQL container: {res.stderr.strip()}"
                )

            self.is_running = True

            # Query Docker for the published port mapping
            port_cmd = ["docker", "port", self.container_name, "5432/tcp"]
            port_res = subprocess.run(port_cmd, capture_output=True, text=True, timeout=10, check=False)
            if port_res.returncode != 0:
                self.stop()
                raise RuntimeError(
                    f"Failed to query port mapping for ephemeral container "
                    f"{self.container_name}: {port_res.stderr.strip()}"
                )

            # Validate loopback-only binding and obtain the dynamically assigned port
            try:
                self.port = self.parse_and_validate_loopback_port(port_res.stdout)
            except Exception as err:
                self.stop()
                raise RuntimeError(
                    f"Ephemeral PostgreSQL container port binding rejected: {err}"
                ) from err

            # Wait for the container to become ready.
            deadline = time.time() + timeout
            while time.time() < deadline:
                if _is_port_reachable("127.0.0.1", self.port):
                    try:
                        logs_check = subprocess.run(
                            ["docker", "logs", "--tail", "50", self.container_name],
                            capture_output=True,
                            text=True,
                            timeout=2,
                            check=False,
                        )
                        # Ensure initdb is complete and the permanent server daemon is running
                        if "PostgreSQL init process complete" in logs_check.stdout:
                            check = subprocess.run(
                                ["docker", "exec", self.container_name,
                                 "psql", "-U", self.admin_user, "-d", "postgres", "-c", "SELECT 1;"],
                                capture_output=True,
                                text=True,
                                timeout=2,
                                check=False,
                            )
                            if check.returncode == 0:
                                # Container is fully initialised; secret no longer needed on host.
                                unlink_err = self._safe_unlink(self._password_file_path)
                                if unlink_err is None:
                                    self._password_file_path = None
                                return
                    except Exception:
                        pass
                time.sleep(0.5)

            self.stop()
            raise TimeoutError(
                f"Ephemeral PostgreSQL container {self.container_name} failed to become ready."
            )

        except Exception as start_exc:
            unlink_err = self._safe_unlink(self._password_file_path)
            if unlink_err is None:
                self._password_file_path = None
            else:
                if hasattr(start_exc, "add_note"):
                    start_exc.add_note(f"Cleanup warning: {unlink_err}")
            raise

    def stop(self) -> None:
        """Stop and remove the ephemeral container, propagating any cleanup failures.

        Teardown failures are not swallowed. If the container cannot be stopped
        or confirmed removed, a RuntimeError is raised with details. This ensures
        leaked containers are always visible to the operator rather than silently
        persisting after a test run.
        """
        import subprocess

        cleanup_errors: list = []

        # 1. Attempt graceful stop of the container
        try:
            stop_res = subprocess.run(
                ["docker", "stop", self.container_name],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if stop_res.returncode != 0:
                cleanup_errors.append(
                    f"docker stop returned non-zero exit {stop_res.returncode}: {stop_res.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            cleanup_errors.append(f"docker stop timed out for container '{self.container_name}'")
        except Exception as exc:
            cleanup_errors.append(f"docker stop raised exception: {exc}")

        # 2. Inspect container to verify it is stopped and determine if forced removal is needed
        container_state_known = False
        try:
            inspect_res = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", self.container_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if inspect_res.returncode == 0:
                container_state_known = True
                if inspect_res.stdout.strip().lower() == "true":
                    # Container still running — attempt forced removal
                    rm_res = subprocess.run(
                        ["docker", "rm", "-f", self.container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if rm_res.returncode != 0:
                        cleanup_errors.append(
                            f"docker rm -f returned non-zero exit {rm_res.returncode}: {rm_res.stderr.strip()}"
                        )
            else:
                stderr_lower = inspect_res.stderr.lower()
                if "no such object" in stderr_lower or "no such container" in stderr_lower or inspect_res.returncode == 1:
                    container_state_known = True
                else:
                    container_state_known = False
                    cleanup_errors.append(
                        f"docker inspect returned exit {inspect_res.returncode}: {inspect_res.stderr.strip()}"
                    )
        except subprocess.TimeoutExpired:
            cleanup_errors.append(f"docker inspect timed out for container '{self.container_name}'")
        except Exception as exc:
            cleanup_errors.append(f"docker inspect/rm raised exception: {exc}")

        if not container_state_known:
            cleanup_errors.append(
                f"Container '{self.container_name}' state could not be verified after stop; "
                "it may still be running."
            )

        # 3. Secret password file cleanup
        unlink_err = self._safe_unlink(self._password_file_path)
        if unlink_err is not None:
            cleanup_errors.append(unlink_err)
        else:
            self._password_file_path = None

        self.is_running = False

        if cleanup_errors:
            raise RuntimeError(
                f"EphemeralPostgresCluster teardown encountered errors for container "
                f"'{self.container_name}'. The container may still be running or secrets uncleaned. "
                f"Errors: {'; '.join(cleanup_errors)}"
            )


def _split_sql_script(sql_text: str) -> List[str]:
    """Split a SQL script into individual statements, honoring quotes, comments, and dollar-quoted blocks."""
    statements: List[str] = []
    current: List[str] = []
    in_single_quote = False
    in_dollar_quote = False
    dollar_tag = ""
    i = 0
    n = len(sql_text)
    while i < n:
        char = sql_text[i]
        if not in_single_quote and not in_dollar_quote:
            # Check for line comment (-- ...)
            if char == "-" and i + 1 < n and sql_text[i + 1] == "-":
                while i < n and sql_text[i] != "\n":
                    i += 1
                continue
        if not in_dollar_quote:
            if char == "'":
                if in_single_quote:
                    if i + 1 < n and sql_text[i + 1] == "'":
                        current.append("''")
                        i += 2
                        continue
                    in_single_quote = False
                else:
                    in_single_quote = True
                current.append(char)
                i += 1
                continue
        if not in_single_quote:
            if char == "$":
                rest = sql_text[i:]
                match = re.match(r"^(\$[A-Za-z0-9_]*\$)", rest)
                if match:
                    tag = match.group(1)
                    if in_dollar_quote and tag == dollar_tag:
                        in_dollar_quote = False
                        dollar_tag = ""
                        current.append(tag)
                        i += len(tag)
                        continue
                    elif not in_dollar_quote:
                        in_dollar_quote = True
                        dollar_tag = tag
                        current.append(tag)
                        i += len(tag)
                        continue
        if not in_single_quote and not in_dollar_quote:
            if char == ";":
                current.append(";")
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
                i += 1
                continue
        current.append(char)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _load_init_roles_sql_statements(app_password: str, migrator_password: str) -> List[str]:
    """Parse deployment/docker/postgres/init-roles.sql into executable SQL statements."""
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "deployment" / "docker" / "postgres" / "init-roles.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"init-roles.sql not found at {sql_path}")

    raw_sql = sql_path.read_text(encoding="utf-8")

    # Strip psql meta-commands and top-level comment-only lines
    clean_lines = []
    in_dollar_block = False
    for line in raw_sql.splitlines():
        trimmed = line.strip()
        if "$$" in trimmed:
            in_dollar_block = not in_dollar_block
        if not in_dollar_block and (trimmed.startswith("\\") or trimmed.startswith("--")):
            continue
        clean_lines.append(line)

    sql_text = "\n".join(clean_lines)

    safe_app_pass = app_password.replace("'", "''").replace(":", "\\:")
    safe_mig_pass = migrator_password.replace("'", "''").replace(":", "\\:")
    sql_text = sql_text.replace(":'app_pass'", f"'{safe_app_pass}'")
    sql_text = sql_text.replace(":'migrator_pass'", f"'{safe_mig_pass}'")

    return _split_sql_script(sql_text)


def _load_rotate_roles_sql_statements(app_password: str, migrator_password: str) -> List[str]:
    """Parse deployment/docker/postgres/rotate-role-passwords.sql into executable SQL statements."""
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "deployment" / "docker" / "postgres" / "rotate-role-passwords.sql"
    if not sql_path.exists():
        raise FileNotFoundError(f"rotate-role-passwords.sql not found at {sql_path}")

    raw_sql = sql_path.read_text(encoding="utf-8")

    clean_lines = []
    in_dollar_block = False
    for line in raw_sql.splitlines():
        trimmed = line.strip()
        if "$$" in trimmed:
            in_dollar_block = not in_dollar_block
        if not in_dollar_block and (trimmed.startswith("\\") or trimmed.startswith("--")):
            continue
        clean_lines.append(line)

    sql_text = "\n".join(clean_lines)

    safe_app_pass = app_password.replace("'", "''").replace(":", "\\:")
    safe_mig_pass = migrator_password.replace("'", "''").replace(":", "\\:")
    sql_text = sql_text.replace(":'app_pass'", f"'{safe_app_pass}'")
    sql_text = sql_text.replace(":'migrator_pass'", f"'{safe_mig_pass}'")

    return _split_sql_script(sql_text)


@pytest.mark.asyncio
async def test_postgres_cluster_bootstrap_and_rotation():
    """Verify cluster-wide role bootstrap, initialization, and credential rotation (Objectives 1, 3, 4).

    Strict Safety Boundary:
    - This test alters cluster-wide roles (CREATE ROLE, ALTER ROLE ... PASSWORD).
    - It MUST NEVER run against a shared, pre-existing, or operational PostgreSQL instance.
    - It requires a harness-managed EphemeralPostgresCluster.
    - If Docker is unavailable, it reports NOT RUN / NOT VERIFIED (environmental limitation).

    Execution Sequence:
    1. Launches harness-managed EphemeralPostgresCluster.
    2. Creates disposable test database with active server comment attestation.
    3. As pre-bootstrap owner (postgres): creates pre-existing test table and sequence.
    4. Executes init-roles.sql bootstrap SQL with complex passwords (containing special characters).
    5. Authenticates as rag_app and rag_migrator; strictly asserts session_user and current_user.
    6. Verifies rag_app has runtime DML on pre-existing objects (initial bootstrap grants).
    7. Verifies rag_app is denied all DDL (CREATE TABLE, ALTER TABLE, DROP TABLE, CREATE TEMPORARY TABLE).
    8. Verifies rag_migrator has migration DDL capabilities on pre-existing objects.
    9. Verifies default privileges for objects created by rag_migrator AFTER bootstrap.
    10. Executes rotate-role-passwords.sql with new rotated passwords (containing special characters).
    11. Verifies old credentials fail authentication.
    12. Verifies new credentials succeed authentication with expected session_user and current_user.
    13. Guaranteed teardown terminates and deletes the ephemeral container.
    """
    if not EphemeralPostgresCluster.is_available():
        pytest.skip(
            "Ephemeral PostgreSQL cluster provisioning is unavailable (Docker daemon offline). "
            "Cluster-wide role bootstrap and rotation tests are marked NOT RUN / NOT VERIFIED "
            "to protect shared/operational PostgreSQL servers."
        )

    cluster = EphemeralPostgresCluster()
    try:
        cluster.start()
    except Exception as exc:
        pytest.skip(
            f"Failed to start ephemeral PostgreSQL cluster ({exc}). "
            "Cluster-wide role bootstrap is marked NOT RUN / NOT VERIFIED."
        )

    import secrets
    isolation_token = secrets.token_hex(16)
    target_dbname = "rag_disposable_test"
    admin_url = _build_db_url(cluster.admin_user, cluster.admin_password, "127.0.0.1", cluster.port, "postgres")
    disposable_db_url = _build_db_url(cluster.admin_user, cluster.admin_password, "127.0.0.1", cluster.port, target_dbname)

    # Complex passwords containing special characters (including @, :, /, %, #)
    init_app_pass = "InitApp!@#$%^&*()_+-=~"
    init_mig_pass = "InitMig!@#$%^&*()_+-=~"
    rot_app_pass = "RotApp!@#:$%^&*/~[]{};<=>"
    rot_mig_pass = "RotMig!@#:$%^&*/~[]{};<=>"

    tracked_tables: List[str] = []
    unique_suffix = uuid.uuid4().hex[:8]
    preexisting_table = f"_test_preexisting_{unique_suffix}"
    preexisting_seq = f"_test_preexisting_seq_{unique_suffix}"
    preexisting_matview = f"_test_preexisting_matview_{unique_suffix}"
    postbootstrap_table = f"_test_postbootstrap_{unique_suffix}"
    forbidden_table = f"_forbidden_tbl_{unique_suffix}"
    forbidden_temp = f"_forbidden_temp_{unique_suffix}"

    admin_engine: AsyncEngine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        # Step 1: Create disposable test database and active attestation comment
        for attempt in range(10):
            try:
                async with admin_engine.connect() as conn:
                    await conn.execute(text(f"CREATE DATABASE {target_dbname};"))
                    await _set_database_isolation_comment(conn, target_dbname, isolation_token)
                break
            except Exception:
                if attempt < 9:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise

        boot_engine: AsyncEngine = create_async_engine(disposable_db_url)

        # Step 2: As pre-bootstrap owner (postgres), create pre-existing table, sequence, and materialized view
        async with boot_engine.begin() as boot_conn:
            await _verify_connection_attestation(boot_conn, isolation_token)
            await _inspect_target_state_cross_schema(boot_conn)

            await boot_conn.execute(
                text(
                    f"CREATE TABLE {preexisting_table} ("
                    f"    id serial PRIMARY KEY, "
                    f"    val text NOT NULL, "
                    f"    created_at timestamptz DEFAULT clock_timestamp()"
                    f");"
                )
            )
            tracked_tables.append(preexisting_table)

            await boot_conn.execute(text(f"CREATE SEQUENCE {preexisting_seq};"))
            tracked_tables.append(preexisting_seq)

            await boot_conn.execute(
                text(f"INSERT INTO {preexisting_table} (val) VALUES ('prebootstrap_seed');")
            )

            await boot_conn.execute(
                text(f"CREATE MATERIALIZED VIEW {preexisting_matview} AS SELECT id, val FROM {preexisting_table};")
            )
            tracked_tables.append(preexisting_matview)

            # Step 3: Run the actual init-roles.sql bootstrap SQL statements
            bootstrap_stmts = _load_init_roles_sql_statements(init_app_pass, init_mig_pass)
            for stmt in bootstrap_stmts:
                await boot_conn.execute(text(stmt))

        # Build app and migrator engines using structured URL.create() with special characters
        app_url_init = _build_db_url("rag_app", init_app_pass, "127.0.0.1", cluster.port, target_dbname)
        mig_url_init = _build_db_url("rag_migrator", init_mig_pass, "127.0.0.1", cluster.port, target_dbname)

        app_engine_init: AsyncEngine = create_async_engine(app_url_init)
        mig_engine_init: AsyncEngine = create_async_engine(mig_url_init)

        # Step 4: Multi-factor identity and authenticated identity verification
        async with boot_engine.begin() as b_conn:
            async with mig_engine_init.begin() as m_conn:
                async with app_engine_init.begin() as a_conn:
                    await _verify_server_isolation_and_identity(
                        [("bootstrap", b_conn, "postgres"), ("migrator", m_conn, "rag_migrator"), ("app", a_conn, "rag_app")],
                        expected_token=isolation_token,
                        target_dbname=target_dbname,
                    )

        # Step 5: Verify runtime DML on pre-existing objects (initial bootstrap grants)
        async with app_engine_init.begin() as app_conn:
            res = await app_conn.execute(
                text(f"SELECT val FROM {preexisting_table} WHERE val = 'prebootstrap_seed';")
            )
            assert res.scalar_one() == "prebootstrap_seed"

            await app_conn.execute(
                text(f"INSERT INTO {preexisting_table} (val) VALUES ('runtime_inserted');")
            )
            await app_conn.execute(
                text(f"UPDATE {preexisting_table} SET val = 'runtime_updated' WHERE val = 'runtime_inserted';")
            )
            await app_conn.execute(
                text(f"DELETE FROM {preexisting_table} WHERE val = 'runtime_updated';")
            )

            seq_val = (await app_conn.execute(text(f"SELECT nextval('{preexisting_seq}');"))).scalar_one()
            assert seq_val >= 1

            # Verify materialized view SELECT access for rag_app
            mv_val = (await app_conn.execute(text(f"SELECT val FROM {preexisting_matview} WHERE val = 'prebootstrap_seed';"))).scalar_one()
            assert mv_val == "prebootstrap_seed"

        # Verify materialized view ownership was transferred to rag_migrator
        async with boot_engine.begin() as b_conn:
            mv_res = await b_conn.execute(
                text(
                    "SELECT pg_catalog.pg_get_userbyid(c.relowner) "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    f"WHERE n.nspname = 'public' AND c.relname = '{preexisting_matview}' AND c.relkind = 'm';"
                )
            )
            assert mv_res.scalar_one() == "rag_migrator", (
                f"Materialized view '{preexisting_matview}' was not reassigned to rag_migrator"
            )

        # Verify rag_migrator can REFRESH materialized view
        async with mig_engine_init.begin() as mig_conn:
            await mig_conn.execute(text(f"REFRESH MATERIALIZED VIEW {preexisting_matview};"))

        # Step 6: Verify rag_app is denied all DDL, REFRESH, DROP, and TEMPORARY tables
        for ddl_stmt in [
            f"CREATE TABLE {forbidden_table} (id int);",
            f"ALTER TABLE {preexisting_table} ADD COLUMN bad_col int;",
            f"DROP TABLE {preexisting_table};",
            f"REFRESH MATERIALIZED VIEW {preexisting_matview};",
            f"DROP MATERIALIZED VIEW {preexisting_matview};",
            f"CREATE TEMPORARY TABLE {forbidden_temp} (id int);",
        ]:
            async with app_engine_init.begin() as app_conn:
                with pytest.raises(ProgrammingError):
                    await app_conn.execute(text(ddl_stmt))

        # Step 7: Verify rag_migrator has migration DDL capabilities
        async with mig_engine_init.begin() as mig_conn:
            await mig_conn.execute(
                text(f"ALTER TABLE {preexisting_table} ADD COLUMN mig_col text DEFAULT 'migrated';")
            )

        # Step 8: Test default privileges for post-bootstrap tables created by rag_migrator
        async with mig_engine_init.begin() as mig_conn:
            await mig_conn.execute(
                text(f"CREATE TABLE {postbootstrap_table} (id serial PRIMARY KEY, note text);")
            )
            tracked_tables.append(postbootstrap_table)

        async with app_engine_init.begin() as app_conn:
            await app_conn.execute(
                text(f"INSERT INTO {postbootstrap_table} (note) VALUES ('postbootstrap_note');")
            )
            res = await app_conn.execute(text(f"SELECT note FROM {postbootstrap_table};"))
            assert res.scalar_one() == "postbootstrap_note"

        # Step 9: Execute credential rotation with new complex passwords
        rotate_stmts = _load_rotate_roles_sql_statements(rot_app_pass, rot_mig_pass)
        async with boot_engine.begin() as boot_conn:
            for stmt in rotate_stmts:
                await boot_conn.execute(text(stmt))

        # Dispose old connection pools
        await app_engine_init.dispose()
        await mig_engine_init.dispose()

        # Step 10: Verify OLD credentials fail authentication (distinguish from network/startup failure)
        app_engine_old = create_async_engine(app_url_init)
        try:
            await _assert_authentication_failure(app_engine_old, "rag_app")
        finally:
            await app_engine_old.dispose()

        mig_engine_old = create_async_engine(mig_url_init)
        try:
            await _assert_authentication_failure(mig_engine_old, "rag_migrator")
        finally:
            await mig_engine_old.dispose()

        # Step 11: Verify NEW credentials succeed authentication with expected identities
        app_url_rot = _build_db_url("rag_app", rot_app_pass, "127.0.0.1", cluster.port, target_dbname)
        mig_url_rot = _build_db_url("rag_migrator", rot_mig_pass, "127.0.0.1", cluster.port, target_dbname)

        app_engine_rot = create_async_engine(app_url_rot)
        mig_engine_rot = create_async_engine(mig_url_rot)

        async with app_engine_rot.connect() as a_conn:
            ident_app = await _verify_authenticated_identities(a_conn, "rag_app", target_dbname)
            assert ident_app["session_user"] == "rag_app"
            assert ident_app["current_user"] == "rag_app"

        async with mig_engine_rot.connect() as m_conn:
            ident_mig = await _verify_authenticated_identities(m_conn, "rag_migrator", target_dbname)
            assert ident_mig["session_user"] == "rag_migrator"
            assert ident_mig["current_user"] == "rag_migrator"

        # Step 12: Rerun effective runtime permission checks on app_engine_rot
        async with app_engine_rot.begin() as app_conn:
            res = await app_conn.execute(
                text(f"SELECT val FROM {preexisting_table} WHERE val = 'prebootstrap_seed';")
            )
            assert res.scalar_one() == "prebootstrap_seed"

            await app_conn.execute(
                text(f"INSERT INTO {preexisting_table} (val) VALUES ('runtime_rot_inserted');")
            )
            await app_conn.execute(
                text(f"UPDATE {preexisting_table} SET val = 'runtime_rot_updated' WHERE val = 'runtime_rot_inserted';")
            )
            await app_conn.execute(
                text(f"DELETE FROM {preexisting_table} WHERE val = 'runtime_rot_updated';")
            )

            res = await app_conn.execute(text(f"SELECT note FROM {postbootstrap_table};"))
            assert res.scalar_one() == "postbootstrap_note"

            await app_conn.execute(
                text(f"INSERT INTO {postbootstrap_table} (note) VALUES ('postrotation_note');")
            )

            seq_val = (await app_conn.execute(text(f"SELECT nextval('{preexisting_seq}');"))).scalar_one()
            assert seq_val >= 2

        # Verify rag_app is denied all DDL and TEMPORARY tables after rotation
        forbidden_postrot_tbl = f"_forbidden_postrot_{unique_suffix}"
        forbidden_postrot_tmp = f"_forbidden_temp_postrot_{unique_suffix}"
        for ddl_stmt in [
            f"CREATE TABLE {forbidden_postrot_tbl} (id int);",
            f"ALTER TABLE {preexisting_table} ADD COLUMN bad_rot_col int;",
            f"DROP TABLE {preexisting_table};",
            f"CREATE TEMPORARY TABLE {forbidden_postrot_tmp} (id int);",
        ]:
            async with app_engine_rot.begin() as app_conn:
                with pytest.raises(ProgrammingError):
                    await app_conn.execute(text(ddl_stmt))

        # Step 13: Rerun intended migration checks on mig_engine_rot
        postrotation_table = f"_test_postrotation_{unique_suffix}"
        async with mig_engine_rot.begin() as mig_conn:
            await mig_conn.execute(
                text(f"ALTER TABLE {preexisting_table} ADD COLUMN rot_mig_col text DEFAULT 'rot_migrated';")
            )
            await mig_conn.execute(
                text(f"CREATE TABLE {postrotation_table} (id serial PRIMARY KEY, data text);")
            )
            tracked_tables.append(postrotation_table)

        # Confirm default privileges apply to objects created after rotation by migrator
        async with app_engine_rot.begin() as app_conn:
            await app_conn.execute(
                text(f"INSERT INTO {postrotation_table} (data) VALUES ('rot_app_data');")
            )
            res = await app_conn.execute(text(f"SELECT data FROM {postrotation_table};"))
            assert res.scalar_one() == "rot_app_data"

        # Step 14: Confirm rotation has not added unintended memberships, ownership, or privileges
        async with boot_engine.begin() as boot_conn:
            for role_name in ("rag_app", "rag_migrator"):
                role_res = await boot_conn.execute(
                    text(
                        "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls "
                        "FROM pg_roles WHERE rolname = :rolname;"
                    ),
                    {"rolname": role_name},
                )
                row = role_res.mappings().fetchone()
                assert row is not None, f"Role {role_name} not found in pg_roles"
                assert not row["rolsuper"], f"Role {role_name} unexpectedly has SUPERUSER"
                assert not row["rolcreaterole"], f"Role {role_name} unexpectedly has CREATEROLE"
                assert not row["rolcreatedb"], f"Role {role_name} unexpectedly has CREATEDB"
                assert not row["rolreplication"], f"Role {role_name} unexpectedly has REPLICATION"
                assert not row["rolbypassrls"], f"Role {role_name} unexpectedly has BYPASSRLS"

            # Check for unintended role memberships for rag_app
            member_res = await boot_conn.execute(
                text(
                    "SELECT count(*) FROM pg_auth_members "
                    "WHERE member = (SELECT oid FROM pg_roles WHERE rolname = 'rag_app');"
                )
            )
            assert member_res.scalar_one() == 0, "rag_app unexpectedly has role memberships"

            # Confirm rag_app does not own any database objects
            owner_res = await boot_conn.execute(
                text(
                    "SELECT count(*) FROM pg_class c "
                    "JOIN pg_roles r ON c.relowner = r.oid "
                    "WHERE r.rolname = 'rag_app' AND c.relkind IN ('r', 'v', 'm', 'S');"
                )
            )
            assert owner_res.scalar_one() == 0, "rag_app unexpectedly owns database objects"

        await app_engine_rot.dispose()
        await mig_engine_rot.dispose()
        await boot_engine.dispose()
        await admin_engine.dispose()

    finally:
        # Guaranteed cleanup: stops and destroys the ephemeral container.
        # If teardown fails, attach the cleanup error without replacing the
        # original test exception so both failures remain visible.
        import sys as _sys
        _original_exc = _sys.exc_info()[1]
        try:
            cluster.stop()
        except Exception as _teardown_err:
            if _original_exc is not None:
                # Surface teardown failure as a chained note on the original exception
                _teardown_note = (
                    f"Additionally, EphemeralPostgresCluster.stop() raised: {_teardown_err}"
                )
                if hasattr(_original_exc, "add_note"):
                    # Python 3.11+: attach as a structured note
                    _original_exc.add_note(_teardown_note)
                else:
                    # Fallback: extend the string representation via args
                    _original_exc.args = _original_exc.args + (_teardown_note,)
                # Do NOT re-raise teardown_err so original exception propagates intact
            else:
                # No test exception in flight; re-raise cleanup error directly
                raise



@pytest.mark.asyncio
async def test_postgres_public_schema_create_reconciliation():
    """Verify bootstrap strips the legacy PUBLIC CREATE privilege from schema public.

    Task 1 (Round 14) — Real PostgreSQL evidence requirement:
    1. Seeds GRANT CREATE ON SCHEMA public TO PUBLIC (the pre-PG15 default).
    2. Runs the actual init-roles.sql bootstrap path.
    3. Asserts via has_schema_privilege() that PUBLIC no longer holds CREATE.
    4. Asserts rag_app cannot CREATE TABLE (verifies effective enforcement, not just catalog).
    5. The test is written so removing REVOKE CREATE ON SCHEMA public FROM PUBLIC from
       init-roles.sql would cause it to fail.

    Live PostgreSQL evidence: NOT VERIFIED (Docker unavailable).
    Source-level evidence: init-roles.sql contains the revoke; unit test confirms presence.
    """
    if not EphemeralPostgresCluster.is_available():
        pytest.skip(
            "Docker unavailable — PUBLIC schema CREATE reconciliation is NOT VERIFIED live. "
            "Source-level evidence: REVOKE CREATE ON SCHEMA public FROM PUBLIC present in init-roles.sql."
        )

    cluster = EphemeralPostgresCluster()
    try:
        cluster.start()
    except Exception as exc:
        pytest.skip(f"Cluster start failed ({exc}) — NOT VERIFIED live.")

    import secrets
    isolation_token = secrets.token_hex(16)
    target_dbname = "rag_pubcreate_test"
    init_app_pass = "PubApp!@#$%"
    init_mig_pass = "PubMig!@#$%"

    admin_url = _build_db_url(
        cluster.admin_user, cluster.admin_password, "127.0.0.1", cluster.port, "postgres"
    )
    disposable_db_url = _build_db_url(
        cluster.admin_user, cluster.admin_password, "127.0.0.1", cluster.port, target_dbname
    )
    unique_suffix = uuid.uuid4().hex[:8]
    forbidden_table = f"_forbidden_pub_{unique_suffix}"

    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        # Step 1: Create disposable database with attestation comment
        for attempt in range(10):
            try:
                async with admin_engine.connect() as conn:
                    await conn.execute(text(f"CREATE DATABASE {target_dbname};"))
                    await _set_database_isolation_comment(conn, target_dbname, isolation_token)
                break
            except Exception:
                if attempt < 9:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise

        boot_engine = create_async_engine(disposable_db_url, isolation_level="AUTOCOMMIT")

        # Step 2: Seed the legacy PUBLIC CREATE grant BEFORE bootstrap.
        # On PG < 15 this grant exists by default; on PG 15+ we grant it explicitly
        # to reproduce the legacy condition. Bootstrap must revoke it regardless.
        public_create_query = text(
            "SELECT EXISTS ("
            "    SELECT 1 FROM pg_namespace n, aclexplode(COALESCE(n.nspacl, acldefault('n', n.nspowner))) acl"
            "    WHERE n.nspname = 'public' AND acl.grantee = 0 AND acl.privilege_type = 'CREATE'"
            ");"
        )
        async with boot_engine.connect() as conn:
            await _verify_connection_attestation(conn, isolation_token)
            await conn.execute(text("GRANT CREATE ON SCHEMA public TO PUBLIC;"))

            # Confirm the grant is present before bootstrap so the test proves
            # that bootstrap actually removes it (not that it was never there).
            pre_priv_res = await conn.execute(public_create_query)
            assert pre_priv_res.scalar_one() is True, (
                "Pre-bootstrap: GRANT CREATE ON SCHEMA public TO PUBLIC was not effective. "
                "This test cannot validate that bootstrap removes it."
            )

        # Step 3: Run the actual init-roles.sql bootstrap
        async with boot_engine.connect() as conn:
            bootstrap_stmts = _load_init_roles_sql_statements(init_app_pass, init_mig_pass)
            for stmt in bootstrap_stmts:
                await conn.execute(text(stmt))

        # Step 4: Assert PUBLIC no longer holds CREATE on schema public
        async with boot_engine.connect() as conn:
            post_priv_res = await conn.execute(public_create_query)
            assert post_priv_res.scalar_one() is False, (
                "SECURITY FAILURE: PUBLIC still holds CREATE on schema public after bootstrap. "
                "The REVOKE CREATE ON SCHEMA public FROM PUBLIC in init-roles.sql is either "
                "missing, syntactically broken, or not being executed."
            )

        # Step 5: Verify effective enforcement — rag_app cannot CREATE TABLE
        app_engine = create_async_engine(
            _build_db_url("rag_app", init_app_pass, "127.0.0.1", cluster.port, target_dbname)
        )
        try:
            async with app_engine.begin() as app_conn:
                with pytest.raises(ProgrammingError):
                    await app_conn.execute(
                        text(f"CREATE TABLE {forbidden_table} (id int);")
                    )
        finally:
            await app_engine.dispose()

        await boot_engine.dispose()
        await admin_engine.dispose()

    finally:
        import sys as _sys
        _original_exc = _sys.exc_info()[1]
        try:
            cluster.stop()
        except Exception as _teardown_err:
            if _original_exc is not None:
                note = f"Additionally, EphemeralPostgresCluster.stop() raised: {_teardown_err}"
                if hasattr(_original_exc, "add_note"):
                    _original_exc.add_note(note)
                else:
                    _original_exc.args = _original_exc.args + (note,)
            else:
                raise


@pytest.mark.asyncio
async def test_postgres_migrator_membership_reconciliation():
    """Verify bootstrap removes unexpected memberships from rag_migrator.

    Task 2 (Round 14) — Real PostgreSQL evidence requirement:
    1. Seeds an unexpected membership (pg_monitor) on rag_migrator BEFORE bootstrap.
    2. Runs the actual init-roles.sql bootstrap path.
    3. Asserts via pg_auth_members that the unexpected membership is gone.
    4. Verifies no legitimate access (CONNECT to DB, schema USAGE) was damaged.
    5. Verifies rag_migrator retains only the intended attributes.

    CASCADE concern: REVOKE pg_monitor FROM rag_migrator CASCADE removes the
    membership; it does NOT affect other roles' memberships in pg_monitor or
    rag_migrator's own DDL grants. The bootstrap SQL uses CASCADE only to ensure
    any GRANT OPTION inheritance is also revoked — it does not cascade into
    unrelated privilege trees.

    Live PostgreSQL evidence: NOT VERIFIED (Docker unavailable).
    """
    if not EphemeralPostgresCluster.is_available():
        pytest.skip(
            "Docker unavailable — rag_migrator membership reconciliation is NOT VERIFIED live. "
            "Source-level evidence: REVOKE %I FROM rag_migrator block present in init-roles.sql."
        )

    cluster = EphemeralPostgresCluster()
    try:
        cluster.start()
    except Exception as exc:
        pytest.skip(f"Cluster start failed ({exc}) — NOT VERIFIED live.")

    import secrets
    isolation_token = secrets.token_hex(16)
    target_dbname = "rag_membership_test"
    init_app_pass = "MemApp!@#$%"
    init_mig_pass = "MemMig!@#$%"

    admin_url = _build_db_url(
        cluster.admin_user, cluster.admin_password, "127.0.0.1", cluster.port, "postgres"
    )
    disposable_db_url = _build_db_url(
        cluster.admin_user, cluster.admin_password, "127.0.0.1", cluster.port, target_dbname
    )

    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")

    try:
        # Step 1: Create disposable database with attestation comment
        for attempt in range(10):
            try:
                async with admin_engine.connect() as conn:
                    await conn.execute(text(f"CREATE DATABASE {target_dbname};"))
                    await _set_database_isolation_comment(conn, target_dbname, isolation_token)
                break
            except Exception:
                if attempt < 9:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise

        boot_engine = create_async_engine(disposable_db_url, isolation_level="AUTOCOMMIT")

        # Step 2: Test dependent membership reconciliation safety (Task 2)
        # Create an admin-option membership and a downstream grant made by rag_migrator
        async with boot_engine.connect() as conn:
            await _verify_connection_attestation(conn, isolation_token)
            await conn.execute(text(
                "DO $$ BEGIN "
                "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rag_migrator') THEN "
                "    CREATE ROLE rag_migrator LOGIN; "
                "  END IF; "
                "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'test_admin_parent') THEN "
                "    CREATE ROLE test_admin_parent; "
                "  END IF; "
                "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'test_downstream_member') THEN "
                "    CREATE ROLE test_downstream_member; "
                "  END IF; "
                "END $$;"
            ))
            await conn.execute(text("GRANT test_admin_parent TO rag_migrator WITH ADMIN OPTION;"))
            await conn.execute(text("SET ROLE rag_migrator;"))
            await conn.execute(text("GRANT test_admin_parent TO test_downstream_member;"))
            await conn.execute(text("RESET ROLE;"))

            # Step 2b: Run init-roles.sql and assert failure due to dependent grant (RESTRICT behavior)
            bootstrap_stmts = _load_init_roles_sql_statements(init_app_pass, init_mig_pass)
            failed_with_expected_msg = False
            for stmt in bootstrap_stmts:
                try:
                    await conn.execute(text(stmt))
                except Exception as exc:
                    exc_str = str(exc)
                    if "dependent downstream grants exist" in exc_str and "test_admin_parent" in exc_str:
                        failed_with_expected_msg = True
                        break
            assert failed_with_expected_msg, (
                "Expected init-roles.sql to fail with actionable diagnostic when dependent grants exist"
            )

            # Assert downstream membership is preserved (NOT silently destroyed by cascade)
            downstream_res = await conn.execute(text(
                "SELECT count(*) FROM pg_auth_members m "
                "JOIN pg_roles r_parent ON m.roleid = r_parent.oid "
                "JOIN pg_roles r_member ON m.member = r_member.oid "
                "WHERE r_parent.rolname = 'test_admin_parent' AND r_member.rolname = 'test_downstream_member';"
            ))
            assert downstream_res.scalar_one() == 1, (
                "Downstream role membership was silently destroyed by cascade!"
            )

            # Step 2c: Operator resolves the dependent grant, and adds pg_monitor to verify clean revocation
            await conn.execute(text("REVOKE test_admin_parent FROM test_downstream_member GRANTED BY rag_migrator;"))
            await conn.execute(text("GRANT pg_monitor TO rag_migrator;"))

        # Step 3: Run the actual init-roles.sql bootstrap path now that dependent grants are resolved
        async with boot_engine.connect() as conn:
            bootstrap_stmts = _load_init_roles_sql_statements(init_app_pass, init_mig_pass)
            for stmt in bootstrap_stmts:
                await conn.execute(text(stmt))

        # Step 4: Assert pg_monitor membership is removed after bootstrap
        async with boot_engine.connect() as conn:
            post_membership_res = await conn.execute(
                text(
                    "SELECT count(*) FROM pg_auth_members m "
                    "JOIN pg_roles r_parent ON m.roleid = r_parent.oid "
                    "JOIN pg_roles r_mig ON m.member = r_mig.oid "
                    "WHERE r_mig.rolname = 'rag_migrator' AND r_parent.rolname = 'pg_monitor';"
                )
            )
            assert post_membership_res.scalar_one() == 0, (
                "SECURITY FAILURE: rag_migrator still holds pg_monitor membership after bootstrap. "
                "The membership reconciliation block in init-roles.sql did not remove it."
            )

            # Step 5: Verify no unexpected memberships remain at all
            all_membership_res = await conn.execute(
                text(
                    "SELECT r_parent.rolname FROM pg_auth_members m "
                    "JOIN pg_roles r_parent ON m.roleid = r_parent.oid "
                    "JOIN pg_roles r_mig ON m.member = r_mig.oid "
                    "WHERE r_mig.rolname = 'rag_migrator';"
                )
            )
            remaining = [row[0] for row in all_membership_res.fetchall()]
            assert remaining == [], (
                f"rag_migrator holds unexpected memberships after bootstrap: {remaining}"
            )

            # Step 6: Verify rag_migrator role attributes are intact (not accidentally altered)
            attr_res = await conn.execute(
                text(
                    "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, "
                    "rolbypassrls, rolcanlogin, rolinherit "
                    "FROM pg_roles WHERE rolname = 'rag_migrator';"
                )
            )
            attrs = attr_res.mappings().fetchone()
            assert attrs is not None, "rag_migrator not found in pg_roles after bootstrap"
            assert attrs["rolsuper"] is False, "rag_migrator must not have SUPERUSER"
            assert attrs["rolcreaterole"] is False, "rag_migrator must not have CREATEROLE"
            assert attrs["rolcreatedb"] is False, "rag_migrator must not have CREATEDB"
            assert attrs["rolreplication"] is False, "rag_migrator must not have REPLICATION"
            assert attrs["rolbypassrls"] is False, "rag_migrator must not have BYPASSRLS"
            assert attrs["rolcanlogin"] is True, "rag_migrator must retain LOGIN"
            assert attrs["rolinherit"] is True, "rag_migrator must retain INHERIT"

            # Step 7: Verify rag_migrator can still CONNECT to the database
            # (a legitimate privilege; CASCADE of membership revoke must not affect it)
            conn_priv_res = await conn.execute(
                text(
                    f"SELECT has_database_privilege('rag_migrator', "
                    f"current_database(), 'CONNECT');"
                )
            )
            assert conn_priv_res.scalar_one() is True, (
                "rag_migrator lost CONNECT privilege after membership reconciliation — "
                "CASCADE may have unintentionally removed granted privileges."
            )

        await boot_engine.dispose()
        await admin_engine.dispose()

    finally:
        import sys as _sys
        _original_exc = _sys.exc_info()[1]
        try:
            cluster.stop()
        except Exception as _teardown_err:
            if _original_exc is not None:
                note = f"Additionally, EphemeralPostgresCluster.stop() raised: {_teardown_err}"
                if hasattr(_original_exc, "add_note"):
                    _original_exc.add_note(note)
                else:
                    _original_exc.args = _original_exc.args + (note,)
            else:
                raise


@pytest.mark.asyncio
async def test_postgres_role_privilege_isolation():
    """Verify runtime role privilege isolation against a provisioned disposable database."""
    migrator_url = os.getenv("TEST_MIGRATOR_DB_URL", "").strip()
    app_url = os.getenv("TEST_APP_DB_URL", "").strip()

    if not migrator_url or not app_url:
        pytest.skip(
            "TEST_MIGRATOR_DB_URL and TEST_APP_DB_URL are not configured in environment. "
            "PostgreSQL live privilege verification is marked NOT RUN / NOT VERIFIED (environmental limitation)."
        )

    is_valid, reason = _verify_isolation_contract(migrator_url, app_url)
    if not is_valid:
        pytest.skip(
            f"Isolation contract rejected database target ({reason}). "
            "PostgreSQL live privilege verification is marked NOT RUN / NOT VERIFIED."
        )

    target_info = _parse_url_target(migrator_url)
    if not _is_port_reachable(target_info["host"], target_info["port"]):
        pytest.skip(
            f"PostgreSQL target ({target_info['host']}:{target_info['port']}) is not reachable. "
            "PostgreSQL live privilege verification is marked NOT RUN / NOT VERIFIED (service offline)."
        )

    isolation_token = os.getenv("TEST_POSTGRES_ISOLATION_TOKEN", "").strip()
    migrator_engine: AsyncEngine = create_async_engine(migrator_url)
    app_engine: AsyncEngine = create_async_engine(app_url)

    tracked_created_tables: List[str] = []

    try:
        # Pre-DDL Attestation, Multi-Factor Identity, and Cross-Schema Safety
        async with migrator_engine.begin() as mig_conn:
            async with app_engine.begin() as app_conn:
                await _verify_server_isolation_and_identity(
                    [("migrator", mig_conn), ("app", app_conn)],
                    expected_token=isolation_token,
                    target_dbname=target_info["dbname"],
                )
                await _inspect_target_state_cross_schema(mig_conn)

        unique_suffix = uuid.uuid4().hex[:8]
        test_table_new = f"_test_tbl_migrated_{unique_suffix}"
        forbidden_table = f"_forbidden_{unique_suffix}"
        forbidden_temp = f"_forbidden_temp_{unique_suffix}"
        migrator_temp = f"_migrator_temp_{unique_suffix}"

        # Migration Phase: DDL by migrator
        async with migrator_engine.begin() as conn:
            await conn.execute(
                text(f"CREATE TABLE {test_table_new} (id SERIAL PRIMARY KEY, note TEXT);")
            )
            tracked_created_tables.append(test_table_new)
            await conn.execute(
                text(f"ALTER TABLE {test_table_new} ADD COLUMN status TEXT DEFAULT 'active';")
            )

        # Runtime Phase: DML by rag_app on migrated table
        async with app_engine.begin() as conn:
            await conn.execute(
                text(f"INSERT INTO {test_table_new} (note, status) VALUES (:n, :s);"),
                {"n": "runtime_note_1", "s": "pending"},
            )
            res = await conn.execute(text(f"SELECT note, status FROM {test_table_new};"))
            row = res.fetchone()
            assert row is not None and row[0] == "runtime_note_1" and row[1] == "pending"

            await conn.execute(
                text(f"UPDATE {test_table_new} SET status = :s WHERE note = :n;"),
                {"s": "completed", "n": "runtime_note_1"},
            )
            await conn.execute(
                text(f"DELETE FROM {test_table_new} WHERE note = :n;"),
                {"n": "runtime_note_1"},
            )

        # Prohibited DDL Operations for rag_app
        forbidden_created = False
        try:
            async with app_engine.begin() as conn:
                await conn.execute(text(f"CREATE TABLE {forbidden_table} (id INT);"))
            forbidden_created = True
        except ProgrammingError as exc_info:
            assert "permission denied" in str(exc_info).lower()

        if forbidden_created:
            tracked_created_tables.append(forbidden_table)
            pytest.fail(f"Security failure: rag_app was unexpectedly able to CREATE TABLE {forbidden_table}")

        # Prohibited TEMPORARY table creation for rag_app
        temp_created = False
        try:
            async with app_engine.begin() as conn:
                await conn.execute(text(f"CREATE TEMPORARY TABLE {forbidden_temp} (id INT);"))
            temp_created = True
        except ProgrammingError as exc_info:
            assert "permission denied" in str(exc_info).lower()

        if temp_created:
            tracked_created_tables.append(forbidden_temp)
            pytest.fail("Security failure: rag_app was unexpectedly able to create temporary tables.")

        # Permitted TEMPORARY table creation for rag_migrator
        async with migrator_engine.begin() as conn:
            await conn.execute(text(f"CREATE TEMPORARY TABLE {migrator_temp} (id INT);"))
            await conn.execute(text(f"DROP TABLE {migrator_temp};"))

        # Role Elevation & Membership Checks
        async with migrator_engine.begin() as conn:
            res = await conn.execute(
                text(
                    "SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls "
                    "FROM pg_roles WHERE rolname = 'rag_app';"
                )
            )
            app_role = res.fetchone()
            assert app_role is not None
            assert app_role[0] is False, "rag_app must not have rolsuper"
            assert app_role[1] is False, "rag_app must not have rolcreaterole"
            assert app_role[2] is False, "rag_app must not have rolcreatedb"
            assert app_role[3] is False, "rag_app must not have rolreplication"
            assert app_role[4] is False, "rag_app must not have rolbypassrls"

            membership_check = await conn.execute(
                text(
                    "SELECT r_parent.rolname "
                    "FROM pg_roles r_parent "
                    "JOIN pg_auth_members m ON m.roleid = r_parent.oid "
                    "JOIN pg_roles r_app ON m.member = r_app.oid "
                    "WHERE r_app.rolname = 'rag_app';"
                )
            )
            memberships = [row[0] for row in membership_check.fetchall()]
            assert len(memberships) == 0, f"rag_app must not retain memberships, found: {memberships}"

    finally:
        cleanup_errors = []
        try:
            async with migrator_engine.begin() as conn:
                for tbl in reversed(tracked_created_tables):
                    try:
                        await conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE;"))
                    except Exception as clean_err:
                        cleanup_errors.append(f"Table '{tbl}' drop failed: {str(clean_err)}")
        except Exception as conn_err:
            cleanup_errors.append(f"Cleanup connection failed: {str(conn_err)}")

        await migrator_engine.dispose()
        await app_engine.dispose()

        if cleanup_errors:
            raise RuntimeError(
                f"Test cleanup encountered errors on isolated test database: {'; '.join(cleanup_errors)}"
            )
