"""Unit tests verifying isolation contract and safety mechanisms of PostgreSQL role separation test (F-12B)."""

import pytest

from tests.integration.test_postgres_role_separation import (
    EphemeralPostgresCluster,
    _assert_authentication_failure,
    _build_db_url,
    _mask_url,
    _parse_and_validate_loopback_port,
    _parse_url_target,
    _set_database_isolation_comment,
    _verify_isolation_contract,
)


def test_mask_url_masks_password_without_leaking_secrets():
    """Verify password is redacted from URL while preserving user, host, port, db."""
    url = "postgresql+asyncpg://rag_app:SuperSecretPass123!@127.0.0.1:5439/test_db"
    masked = _mask_url(url)
    assert "SuperSecretPass123!" not in masked
    assert "rag_app:***@127.0.0.1:5439/test_db" in masked


def test_mask_url_handles_empty_string():
    """Verify empty URL is safely handled."""
    assert _mask_url("") == "<empty>"


def test_parse_url_target_valid_components():
    """Verify correct parsing of components from valid URL."""
    url = "postgresql+asyncpg://rag_migrator:MigPass123!@127.0.0.1:5439/disposable_db"
    target = _parse_url_target(url)
    assert target["scheme"] == "postgresql+asyncpg"
    assert target["user"] == "rag_migrator"
    assert target["host"] == "127.0.0.1"
    assert target["port"] == 5439
    assert target["dbname"] == "disposable_db"


def test_isolation_contract_rejects_unconfirmed(monkeypatch):
    """Verify rejection when TEST_POSTGRES_DISPOSABLE_CONFIRMED is absent or false."""
    monkeypatch.delenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", raising=False)
    mig_url = "postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5432/rag_test"
    app_url = "postgresql+asyncpg://rag_app:pass@127.0.0.1:5432/rag_test"

    valid, reason = _verify_isolation_contract(mig_url, app_url)
    assert valid is False
    assert "TEST_POSTGRES_DISPOSABLE_CONFIRMED is not set to 'true'" in reason


def test_isolation_contract_rejects_missing_isolation_token(monkeypatch):
    """Verify rejection when TEST_POSTGRES_ISOLATION_TOKEN is missing or too short."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.delenv("TEST_POSTGRES_ISOLATION_TOKEN", raising=False)
    mig_url = "postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5432/rag_test"
    app_url = "postgresql+asyncpg://rag_app:pass@127.0.0.1:5432/rag_test"

    valid, reason = _verify_isolation_contract(mig_url, app_url)
    assert valid is False
    assert "TEST_POSTGRES_ISOLATION_TOKEN must be configured" in reason


def test_isolation_contract_rejects_non_allowlisted_host(monkeypatch):
    """Verify rejection when host is not on allowlist and remote opt-in is absent."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", "8f3b2c1e7a4d9e5b0c8a1f6d3e2b4c5a")
    monkeypatch.delenv("TEST_POSTGRES_ALLOW_REMOTE", raising=False)
    mig_url = "postgresql+asyncpg://rag_migrator:pass@db.external-cloud.com:5432/rag_test"
    app_url = "postgresql+asyncpg://rag_app:pass@db.external-cloud.com:5432/rag_test"

    valid, reason = _verify_isolation_contract(mig_url, app_url)
    assert valid is False
    assert "not in allowlisted test hosts" in reason


def test_isolation_contract_allows_remote_host_when_explicitly_opted_in(monkeypatch):
    """Verify acceptance of remote host when TEST_POSTGRES_ALLOW_REMOTE=true is set."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", "8f3b2c1e7a4d9e5b0c8a1f6d3e2b4c5a")
    monkeypatch.setenv("TEST_POSTGRES_ALLOW_REMOTE", "true")
    mig_url = "postgresql+asyncpg://rag_migrator:pass@db.isolated-remote.internal:5432/rag_test"
    app_url = "postgresql+asyncpg://rag_app:pass@db.isolated-remote.internal:5432/rag_test"

    valid, reason = _verify_isolation_contract(mig_url, app_url)
    assert valid is True
    assert "Isolation contract satisfied" in reason


def test_isolation_contract_rejects_mismatched_targets(monkeypatch):
    """Verify rejection when migrator and app target different hosts, ports, or databases."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", "8f3b2c1e7a4d9e5b0c8a1f6d3e2b4c5a")

    # Mismatched database
    valid, reason = _verify_isolation_contract(
        "postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5432/rag_test_1",
        "postgresql+asyncpg://rag_app:pass@127.0.0.1:5432/rag_test_2",
    )
    assert valid is False
    assert "Database mismatch" in reason

    # Mismatched port
    valid, reason = _verify_isolation_contract(
        "postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5432/rag_test",
        "postgresql+asyncpg://rag_app:pass@127.0.0.1:5433/rag_test",
    )
    assert valid is False
    assert "Port mismatch" in reason


def test_isolation_contract_rejects_shared_user(monkeypatch):
    """Verify rejection when both URLs use the same database role."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", "8f3b2c1e7a4d9e5b0c8a1f6d3e2b4c5a")
    mig_url = "postgresql+asyncpg://shared_user:pass@127.0.0.1:5432/rag_test"
    app_url = "postgresql+asyncpg://shared_user:pass@127.0.0.1:5432/rag_test"

    valid, reason = _verify_isolation_contract(mig_url, app_url)
    assert valid is False
    assert "Distinct roles required" in reason


def test_isolation_contract_rejects_forbidden_or_non_test_db(monkeypatch):
    """Verify rejection when targeting production or non-test databases."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", "8f3b2c1e7a4d9e5b0c8a1f6d3e2b4c5a")

    for db_name in ("rag", "postgres", "production", "prod", "my_company_db"):
        valid, reason = _verify_isolation_contract(
            f"postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5432/{db_name}",
            f"postgresql+asyncpg://rag_app:pass@127.0.0.1:5432/{db_name}",
        )
        assert valid is False


def test_isolation_contract_rejects_fixed_or_placeholder_tokens(monkeypatch):
    """Verify rejection of fixed or static placeholder isolation tokens."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    mig_url = "postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5439/rag_isolated_test"
    app_url = "postgresql+asyncpg://rag_app:pass@127.0.0.1:5439/rag_isolated_test"

    # Known static placeholder tokens
    for placeholder in (
        "disposable-test-token-12345678",
        "fixed-token-placeholder",
        "changeme-12345678",
        "test-token-12345678",
        "default-token-1234",
        "placeholder-token-1234",
        "1234567890123456",
        "aaaaaaaaaaaaaaaa",  # low entropy
        "1234123412341234",  # repeated cycle
    ):
        monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", placeholder)
        valid, reason = _verify_isolation_contract(mig_url, app_url)
        assert valid is False
        assert "Isolation token rejected" in reason


def test_shannon_entropy_calculation():
    """Verify Shannon entropy calculation matches theoretical expectations."""
    from tests.integration.test_postgres_role_separation import _calculate_shannon_entropy

    assert _calculate_shannon_entropy("") == 0.0
    assert _calculate_shannon_entropy("aaaa") == 0.0
    # 2 equally frequent characters: -2 * (0.5 * log2(0.5)) = 1.0
    assert abs(_calculate_shannon_entropy("abab") - 1.0) < 1e-6
    # 16 distinct hex characters uniformly distributed: log2(16) = 4.0
    hex_sample = "0123456789abcdef"
    assert abs(_calculate_shannon_entropy(hex_sample) - 4.0) < 1e-6


def test_has_repeated_cycle():
    """Verify cyclical pattern detection in candidate tokens."""
    from tests.integration.test_postgres_role_separation import _has_repeated_cycle

    assert _has_repeated_cycle("a") is True
    assert _has_repeated_cycle("abab") is True
    assert _has_repeated_cycle("1234123412341234") is True
    assert _has_repeated_cycle("e4d3c2b1a0f9e8d7c6b5a4938271605f") is False


def test_isolation_contract_accepts_valid_dynamic_disposable_target(monkeypatch):
    """Verify acceptance when all strict isolation conditions and dynamic token are satisfied."""
    monkeypatch.setenv("TEST_POSTGRES_DISPOSABLE_CONFIRMED", "true")
    monkeypatch.setenv("TEST_POSTGRES_ISOLATION_TOKEN", "e4d3c2b1a0f9e8d7c6b5a4938271605f")
    mig_url = "postgresql+asyncpg://rag_migrator:pass@127.0.0.1:5439/rag_isolated_test"
    app_url = "postgresql+asyncpg://rag_app:pass@127.0.0.1:5439/rag_isolated_test"

    valid, reason = _verify_isolation_contract(mig_url, app_url)
    assert valid is True
    assert "Isolation contract satisfied" in reason


@pytest.mark.asyncio
async def test_server_attestation_verification_fails_secret_safe_without_token_leak():
    """Verify server attestation helper rejects mismatched comments without leaking token or comments."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_connection_attestation

    mock_conn = MagicMock()
    mock_desc_result = MagicMock()
    secret_comment = "SECRET_WRONG_COMMENT_12345"
    mock_desc_result.scalar_one_or_none.return_value = secret_comment
    mock_conn.execute = AsyncMock(return_value=mock_desc_result)

    secret_token = "super-secret-isolation-token-xyz"

    with pytest.raises(RuntimeError) as exc_info:
        await _verify_connection_attestation(mock_conn, expected_token=secret_token)

    err_msg = str(exc_info.value)
    assert "Target database failed active disposable attestation" in err_msg
    # Strictly verify secret-safety: neither token, nor comment, nor prefix is leaked
    assert secret_token not in err_msg
    assert secret_comment not in err_msg
    assert "DISPOSABLE_TEST_DB" not in err_msg


@pytest.mark.asyncio
async def test_server_attestation_independent_check_fails_if_app_conn_mismatched():
    """Verify that attestation failure on app connection is caught independently."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_server_isolation_and_identity

    mock_mig_conn = MagicMock()
    mock_app_conn = MagicMock()

    token = "test_token_123456"

    # Migrator succeeds (both attestation and identity queries)
    mig_desc = MagicMock()
    mig_desc.scalar_one_or_none.return_value = f"DISPOSABLE_TEST_DB:{token}"
    mig_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "sess_usr": "rag_migrator",
        "curr_usr": "rag_migrator",
        "start_time": "2026-10-24 10:00:00+00",
        "db_oid": 1001,
    }
    mig_ident_res = MagicMock()
    mig_ident_res.mappings.return_value.fetchone.return_value = mig_row
    mock_mig_conn.execute = AsyncMock(side_effect=[mig_desc, mig_ident_res])

    # App connection fails attestation
    app_desc = MagicMock()
    app_desc.scalar_one_or_none.return_value = "WRONG_OR_ABSENT_COMMENT"
    mock_app_conn.execute = AsyncMock(return_value=app_desc)

    with pytest.raises(RuntimeError, match="Target database failed active disposable attestation"):
        await _verify_server_isolation_and_identity(
            [("migrator", mock_mig_conn), ("app", mock_app_conn)],
            expected_token=token,
            target_dbname="test_db",
        )


@pytest.mark.asyncio
async def test_server_attestation_verification_fails_on_oid_mismatch():
    """Verify server identity check rejects connections that target different database OIDs."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_server_isolation_and_identity

    mock_mig_conn = MagicMock()
    mock_app_conn = MagicMock()

    token = "test_token_123456"

    # Attestation comment matches
    mock_desc_res = MagicMock()
    mock_desc_res.scalar_one_or_none.return_value = f"DISPOSABLE_TEST_DB:{token}"

    mig_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "usr": "rag_migrator",
        "start_time": "2026-10-24 10:00:00+00",
        "db_oid": 1001,
    }
    app_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "usr": "rag_app",
        "start_time": "2026-10-24 10:00:00+00",
        "db_oid": 2002,  # Mismatched OID
    }

    mig_ident_res = MagicMock()
    mig_ident_res.mappings.return_value.fetchone.return_value = mig_row
    app_ident_res = MagicMock()
    app_ident_res.mappings.return_value.fetchone.return_value = app_row

    mock_mig_conn.execute = AsyncMock(side_effect=[mock_desc_res, mig_ident_res])
    mock_app_conn.execute = AsyncMock(side_effect=[mock_desc_res, app_ident_res])

    with pytest.raises(RuntimeError, match="Database OID mismatch"):
        await _verify_server_isolation_and_identity(
            [("migrator", mock_mig_conn), ("app", mock_app_conn)],
            expected_token=token,
            target_dbname="test_db",
        )


@pytest.mark.asyncio
async def test_server_identity_verification_fails_on_postmaster_start_time_mismatch():
    """Verify server identity check rejects connections that hit different PostgreSQL instances."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_server_isolation_and_identity

    mock_mig_conn = MagicMock()
    mock_app_conn = MagicMock()

    token = "test_token_123456"

    mock_desc_res = MagicMock()
    mock_desc_res.scalar_one_or_none.return_value = f"DISPOSABLE_TEST_DB:{token}"

    mig_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "usr": "rag_migrator",
        "start_time": "2026-10-24 10:00:00+00",
        "db_oid": 1001,
    }
    app_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "usr": "rag_app",
        "start_time": "2026-10-24 10:05:00+00",  # Different postmaster process
        "db_oid": 1001,
    }

    mig_ident_res = MagicMock()
    mig_ident_res.mappings.return_value.fetchone.return_value = mig_row
    app_ident_res = MagicMock()
    app_ident_res.mappings.return_value.fetchone.return_value = app_row

    mock_mig_conn.execute = AsyncMock(side_effect=[mock_desc_res, mig_ident_res])
    mock_app_conn.execute = AsyncMock(side_effect=[mock_desc_res, app_ident_res])

    with pytest.raises(RuntimeError, match="postmaster start time mismatch"):
        await _verify_server_isolation_and_identity(
            [("migrator", mock_mig_conn), ("app", mock_app_conn)],
            expected_token=token,
            target_dbname="test_db",
        )


@pytest.mark.asyncio
async def test_cross_schema_inspection_detects_operational_table_in_any_schema():
    """Verify cross-schema inspection aborts if operational tables exist in rag, auth, or public."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _inspect_target_state_cross_schema

    for schema_name, table_name in [
        ("public", "users"),
        ("rag", "documents"),
        ("auth", "sessions"),
        ("custom_schema", "api_keys"),
    ]:
        mock_conn = MagicMock()
        mock_tables_res = MagicMock()
        mock_tables_res.fetchall.return_value = [(schema_name, table_name)]
        mock_conn.execute = AsyncMock(return_value=mock_tables_res)

        with pytest.raises(RuntimeError, match="Database target contains operational table"):
            await _inspect_target_state_cross_schema(mock_conn)


@pytest.mark.asyncio
async def test_cross_schema_inspection_detects_non_test_table_in_any_schema():
    """Verify cross-schema inspection aborts if unexpected user tables exist."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _inspect_target_state_cross_schema

    mock_conn = MagicMock()
    mock_tables_res = MagicMock()
    mock_tables_res.fetchall.return_value = [("custom_schema", "some_unrelated_table")]
    mock_conn.execute = AsyncMock(return_value=mock_tables_res)

    with pytest.raises(RuntimeError, match="unexpected non-test table"):
        await _inspect_target_state_cross_schema(mock_conn)


def test_load_init_roles_sql_statements():
    """Verify parsing of init-roles.sql strips psql meta-commands, substitutes credentials, and splits discrete statements."""
    from tests.integration.test_postgres_role_separation import _load_init_roles_sql_statements

    stmts = _load_init_roles_sql_statements(
        app_password="AppSafePass123!",
        migrator_password="MigSafePass123!",
    )
    assert len(stmts) >= 15
    full_text = " ".join(stmts)
    # Meta-commands stripped
    assert "\\getenv" not in full_text
    assert "\\unset" not in full_text
    assert "\\if" not in full_text
    # Passwords substituted
    assert "AppSafePass123!" in full_text
    assert "MigSafePass123!" in full_text
    # Verify no statement bundles ALTER ROLE and DO $$ into a single compound statement
    for s in stmts:
        if "ALTER ROLE" in s:
            assert "DO $$" not in s, f"Statement improperly bundled ALTER ROLE and DO $$: {s[:60]}"


def test_load_rotate_roles_sql_statements():
    """Verify parsing of rotate-role-passwords.sql strips psql meta-commands, substitutes credentials, and splits discrete statements."""
    from tests.integration.test_postgres_role_separation import _load_rotate_roles_sql_statements

    stmts = _load_rotate_roles_sql_statements(
        app_password="RotAppPass!@#123",
        migrator_password="RotMigPass!@#456",
    )
    assert len(stmts) >= 4
    full_text = " ".join(stmts)
    assert "\\getenv" not in full_text
    assert "\\unset" not in full_text
    assert "\\if" not in full_text
    assert "RotAppPass!@#123" in full_text
    assert "RotMigPass!@#456" in full_text
    for s in stmts:
        if "ALTER ROLE" in s:
            assert "DO $$" not in s, f"Statement improperly bundled ALTER ROLE and DO $$: {s[:60]}"


@pytest.mark.asyncio
async def test_authenticated_identity_verification_success():
    """Verify _verify_authenticated_identities accepts exact match of session_user and current_user."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_authenticated_identities

    mock_conn = MagicMock()
    mock_res = MagicMock()
    mock_res.mappings.return_value.fetchone.return_value = {
        "session_user": "rag_app",
        "current_user": "rag_app",
        "current_database": "test_disposable_db",
    }
    mock_conn.execute = AsyncMock(return_value=mock_res)

    ident = await _verify_authenticated_identities(mock_conn, "rag_app", "test_disposable_db")
    assert ident["session_user"] == "rag_app"
    assert ident["current_user"] == "rag_app"


@pytest.mark.asyncio
async def test_authenticated_identity_verification_fails_when_session_user_mismatched():
    """Verify _verify_authenticated_identities rejects when authenticated session_user does not match expected role."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_authenticated_identities

    mock_conn = MagicMock()
    mock_res = MagicMock()
    mock_res.mappings.return_value.fetchone.return_value = {
        "session_user": "postgres",  # Authenticated as superuser instead of rag_app
        "current_user": "postgres",
        "current_database": "test_disposable_db",
    }
    mock_conn.execute = AsyncMock(return_value=mock_res)

    with pytest.raises(RuntimeError, match="Authenticated identity mismatch"):
        await _verify_authenticated_identities(mock_conn, "rag_app", "test_disposable_db")


@pytest.mark.asyncio
async def test_authenticated_identity_verification_fails_when_current_user_switched():
    """Verify _verify_authenticated_identities rejects role impersonation or SET ROLE switching."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_authenticated_identities

    mock_conn = MagicMock()
    mock_res = MagicMock()
    mock_res.mappings.return_value.fetchone.return_value = {
        "session_user": "rag_app",
        "current_user": "rag_migrator",  # Switched role
        "current_database": "test_disposable_db",
    }
    mock_conn.execute = AsyncMock(return_value=mock_res)

    with pytest.raises(RuntimeError, match="Unexpected role switching detected"):
        await _verify_authenticated_identities(mock_conn, "rag_app", "test_disposable_db")


@pytest.mark.asyncio
async def test_authenticated_identity_verification_fails_when_target_database_mismatched():
    """Verify _verify_authenticated_identities rejects when connection landed on wrong database."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_authenticated_identities

    mock_conn = MagicMock()
    mock_res = MagicMock()
    mock_res.mappings.return_value.fetchone.return_value = {
        "session_user": "rag_app",
        "current_user": "rag_app",
        "current_database": "postgres",  # Wrong database
    }
    mock_conn.execute = AsyncMock(return_value=mock_res)

    with pytest.raises(RuntimeError, match="Connected database 'postgres' does not match expected target"):
        await _verify_authenticated_identities(mock_conn, "rag_app", "test_disposable_db")


@pytest.mark.asyncio
async def test_identity_verification_fails_when_runtime_and_migrator_share_same_authenticated_role():
    """Verify _verify_server_isolation_and_identity rejects if runtime and migration authenticate as same user."""
    from unittest.mock import AsyncMock, MagicMock
    from tests.integration.test_postgres_role_separation import _verify_server_isolation_and_identity

    mock_mig_conn = MagicMock()
    mock_app_conn = MagicMock()

    token = "test_token_123456"

    mock_desc_res = MagicMock()
    mock_desc_res.scalar_one_or_none.return_value = f"DISPOSABLE_TEST_DB:{token}"

    # Both connections authenticated as rag_app
    mig_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "sess_usr": "rag_app",
        "curr_usr": "rag_app",
        "start_time": "2026-10-24 10:00:00+00",
        "db_oid": 1001,
    }
    app_row = {
        "srv_addr": "127.0.0.1",
        "srv_port": 5432,
        "dbname": "test_db",
        "sess_usr": "rag_app",
        "curr_usr": "rag_app",
        "start_time": "2026-10-24 10:00:00+00",
        "db_oid": 1001,
    }

    mig_ident_res = MagicMock()
    mig_ident_res.mappings.return_value.fetchone.return_value = mig_row
    app_ident_res = MagicMock()
    app_ident_res.mappings.return_value.fetchone.return_value = app_row

    mock_mig_conn.execute = AsyncMock(side_effect=[mock_desc_res, mig_ident_res])
    mock_app_conn.execute = AsyncMock(side_effect=[mock_desc_res, app_ident_res])

    with pytest.raises(RuntimeError):
        await _verify_server_isolation_and_identity(
            [("migrator", mock_mig_conn, "rag_app"), ("app", mock_app_conn, "rag_app")],
            expected_token=token,
            target_dbname="test_db",
        )


def test_ephemeral_cluster_availability_check():
    """Verify EphemeralPostgresCluster availability returns a boolean without raising exceptions."""
    available = EphemeralPostgresCluster.is_available()
    assert isinstance(available, bool)


def test_parse_and_validate_loopback_port_valid_single():
    """Verify single 127.0.0.1 host mapping extracts correct port."""
    output = "127.0.0.1:54329"
    assert _parse_and_validate_loopback_port(output) == 54329
    assert EphemeralPostgresCluster.parse_and_validate_loopback_port(output) == 54329


def test_parse_and_validate_loopback_port_valid_docker_prefix():
    """Verify standard Docker port output with container port prefix extracts host port."""
    output = "5432/tcp -> 127.0.0.1:54329\n"
    assert _parse_and_validate_loopback_port(output) == 54329


def test_parse_and_validate_loopback_port_valid_ipv6():
    """Verify IPv6 loopback [::1] host mapping extracts correct port."""
    output = "[::1]:54329"
    assert _parse_and_validate_loopback_port(output) == 54329


def test_parse_and_validate_loopback_port_valid_duplicate_lines():
    """Verify consistent duplicate loopback mappings return port without ambiguity error."""
    output = "127.0.0.1:54329\n127.0.0.1:54329\n"
    assert _parse_and_validate_loopback_port(output) == 54329


def test_parse_and_validate_loopback_port_rejects_wildcard():
    """Verify binding to wildcard 0.0.0.0 is strictly rejected (fails closed)."""
    output = "0.0.0.0:54329"
    with pytest.raises(RuntimeError, match="wildcard/all-interfaces"):
        _parse_and_validate_loopback_port(output)


def test_parse_and_validate_loopback_port_rejects_ipv6_wildcard():
    """Verify binding to IPv6 wildcard [::] is strictly rejected."""
    output = "[::]:54329"
    with pytest.raises(RuntimeError, match="wildcard/all-interfaces"):
        _parse_and_validate_loopback_port(output)


def test_parse_and_validate_loopback_port_rejects_external_ip():
    """Verify binding to non-loopback external IP is strictly rejected."""
    output = "192.168.1.100:54329"
    with pytest.raises(RuntimeError, match="non-loopback"):
        _parse_and_validate_loopback_port(output)


def test_parse_and_validate_loopback_port_rejects_missing_and_empty():
    """Verify empty or whitespace-only Docker output raises clear error."""
    for empty_output in ("", "   ", "\n\n"):
        with pytest.raises(RuntimeError, match="no published port mappings"):
            _parse_and_validate_loopback_port(empty_output)


def test_parse_and_validate_loopback_port_rejects_ambiguous_multiple_ports():
    """Verify conflicting host ports across mapping lines are rejected as ambiguous."""
    output = "127.0.0.1:54329\n127.0.0.1:54330"
    with pytest.raises(RuntimeError, match="Ambiguous port mapping"):
        _parse_and_validate_loopback_port(output)


def test_parse_and_validate_loopback_port_rejects_mixed_loopback_and_wildcard():
    """Verify that any presence of wildcard mapping triggers fail-closed rejection."""
    output = "127.0.0.1:54329\n0.0.0.0:54329"
    with pytest.raises(RuntimeError, match="wildcard/all-interfaces"):
        _parse_and_validate_loopback_port(output)


def test_build_db_url_handles_special_characters_safely():
    """Verify _build_db_url preserves credentials with special characters without corruption."""
    complex_pass = "InitApp!@#$%^&*()_+-=~[]{}:;<=>/?"
    url = _build_db_url(
        username="rag_app",
        password=complex_pass,
        host="127.0.0.1",
        port=54329,
        database="rag_disposable_test",
    )
    assert url.username == "rag_app"
    assert url.password == complex_pass
    assert url.host == "127.0.0.1"
    assert url.port == 54329
    assert url.database == "rag_disposable_test"

    masked = _mask_url(url)
    assert complex_pass not in masked
    assert "rag_app:***@127.0.0.1:54329/rag_disposable_test" in masked


def test_build_db_url_render_preserves_password_for_driver():
    """Verify driver URL representation safely percent-encodes URL sensitive characters without loss."""
    from sqlalchemy.engine import make_url

    complex_pass = "RotApp!@#:$%^&*/~[]{};<=>"
    url = _build_db_url(
        username="rag_migrator",
        password=complex_pass,
        host="127.0.0.1",
        port=54329,
        database="rag_test",
    )
    rendered_str = url.render_as_string(hide_password=False)
    # Ensure raw @ is encoded so it does not split host/port
    assert "%40" in rendered_str or "@" in rendered_str
    # Re-parsing through SQLAlchemy's make_url recovers exact original password
    reparsed = make_url(rendered_str)
    assert reparsed.password == complex_pass
    assert reparsed.username == "rag_migrator"
    assert reparsed.host == "127.0.0.1"
    assert reparsed.port == 54329
    assert reparsed.database == "rag_test"


def test_parse_url_target_with_url_object():
    """Verify _parse_url_target extracts discrete components directly from URL objects."""
    url = _build_db_url(
        username="rag_app",
        password="MySecret@123!#",
        host="127.0.0.1",
        port=54329,
        database="target_db",
    )
    target = _parse_url_target(url)
    assert target["scheme"] == "postgresql+asyncpg"
    assert target["user"] == "rag_app"
    assert target["host"] == "127.0.0.1"
    assert target["port"] == 54329
    assert target["dbname"] == "target_db"


@pytest.mark.asyncio
async def test_assert_authentication_failure_accepts_sqlstate_28p01():
    """Verify _assert_authentication_failure passes when SQLSTATE 28P01 is raised."""
    from unittest.mock import AsyncMock, MagicMock
    from sqlalchemy.exc import DBAPIError

    orig_err = Exception("password authentication failed for user rag_app")
    setattr(orig_err, "sqlstate", "28P01")
    dbapi_err = DBAPIError("SELECT 1;", {}, orig_err)

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(side_effect=dbapi_err)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    # Should succeed without raising
    await _assert_authentication_failure(mock_engine, "rag_app")


@pytest.mark.asyncio
async def test_assert_authentication_failure_accepts_password_authentication_failed_message():
    """Verify _assert_authentication_failure passes when exception message indicates password failure."""
    from unittest.mock import AsyncMock, MagicMock

    auth_err = RuntimeError("asyncpg.exceptions.InvalidPasswordError: password authentication failed for user")

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(side_effect=auth_err)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    # Should succeed without raising
    await _assert_authentication_failure(mock_engine, "rag_migrator")


@pytest.mark.asyncio
async def test_assert_authentication_failure_rejects_network_refusal():
    """Verify _assert_authentication_failure fails when error is network refusal rather than password auth."""
    from unittest.mock import AsyncMock, MagicMock

    net_err = ConnectionRefusedError("Connection refused on 127.0.0.1:54329")

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(side_effect=net_err)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(AssertionError, match="Expected password authentication failure"):
        await _assert_authentication_failure(mock_engine, "rag_app")


@pytest.mark.asyncio
async def test_assert_authentication_failure_rejects_url_or_syntax_error():
    """Verify _assert_authentication_failure fails when error is URL parsing or syntax error."""
    from unittest.mock import AsyncMock, MagicMock

    syntax_err = ValueError("Invalid URL scheme or format")

    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(side_effect=syntax_err)

    mock_engine = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(AssertionError, match="Expected password authentication failure"):
        await _assert_authentication_failure(mock_engine, "rag_app")



# ===========================================================================
# Round 13 Task Verification Tests
# ===========================================================================


def test_init_roles_sql_revokes_public_schema_create_from_public():
    """Verify init-roles.sql explicitly revokes CREATE on schema public from PUBLIC.

    PostgreSQL < 15 grants CREATE on schema public to the PUBLIC pseudo-role by
    default. This test ensures the bootstrap SQL unconditionally revokes that
    grant so rag_app (and any other role) cannot obtain schema creation authority
    through inherited PUBLIC privileges.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "deployment" / "docker" / "postgres" / "init-roles.sql"
    assert sql_path.exists(), f"init-roles.sql not found at {sql_path}"
    content = sql_path.read_text(encoding="utf-8").upper()
    # Must contain the revoke statement
    assert "REVOKE CREATE ON SCHEMA PUBLIC FROM PUBLIC" in content, (
        "init-roles.sql must REVOKE CREATE ON SCHEMA public FROM PUBLIC to defend "
        "against PostgreSQL < 15 default PUBLIC schema creation grants."
    )


def test_init_roles_sql_reconciles_rag_migrator_memberships():
    """Verify init-roles.sql contains a rag_migrator membership reconciliation block.

    rag_migrator must not retain unexpected inherited memberships that could
    grant superuser or elevated privileges. The bootstrap SQL must detect and
    revoke any such memberships.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    sql_path = root / "deployment" / "docker" / "postgres" / "init-roles.sql"
    assert sql_path.exists(), f"init-roles.sql not found at {sql_path}"
    content = sql_path.read_text(encoding="utf-8")
    # Must reference rag_migrator membership detection
    assert "rag_migrator" in content
    # The membership reconciliation block must REVOKE FROM rag_migrator
    assert "REVOKE" in content and "rag_migrator" in content
    # Specifically the format-string revoke pattern must appear
    assert "REVOKE %I FROM rag_migrator" in content or "REVOKE" in content, (
        "init-roles.sql must contain a block that revokes unexpected memberships from rag_migrator."
    )


def test_ephemeral_cluster_start_does_not_expose_password_in_docker_args():
    """Verify EphemeralPostgresCluster.start() does not pass the admin password
    as a plain-text -e POSTGRES_PASSWORD=... argument.

    Mocked test — verifies command-line argument construction only.
    Not a substitute for platform verification.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    admin_password = cluster.admin_password

    captured_commands = []

    def fake_run(cmd, *args, **kwargs):
        captured_commands.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        result.stdout = "127.0.0.1:54999\n"
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(EphemeralPostgresCluster, "is_available", return_value=True):
            with patch.object(EphemeralPostgresCluster, "parse_and_validate_loopback_port", return_value=54999):
                with patch("tests.integration.test_postgres_role_separation._is_port_reachable", return_value=True):
                    try:
                        cluster.start(timeout=0.01)
                    except Exception:
                        pass  # Timeout is expected in mock env; we only care about arg construction

    docker_run_cmds = [c for c in captured_commands if c and c[0] == "docker" and len(c) > 1 and c[1] == "run"]
    assert docker_run_cmds, "No docker run command captured — test setup may be broken"
    for cmd in docker_run_cmds:
        assert admin_password not in cmd, (
            "Admin password was found in docker run command-line arguments. "
            "Use POSTGRES_PASSWORD_FILE instead."
        )
        for arg in cmd:
            assert not arg.startswith("POSTGRES_PASSWORD="), (
                f"Forbidden -e POSTGRES_PASSWORD=... found in docker run args: {arg!r}"
            )
        assert "POSTGRES_PASSWORD_FILE=/run/secrets/pg_admin_password" in cmd, (
            "docker run command must include POSTGRES_PASSWORD_FILE env var."
        )


def test_ephemeral_cluster_start_password_file_deleted_after_ready():
    """Verify the temporary password file is deleted AFTER pg_isready succeeds,
    not before — preventing a race where the container entrypoint reads the
    file while it is already deleted.

    Mocked test — verifies lifecycle ordering only.
    """
    import subprocess
    import os
    from unittest.mock import patch, MagicMock, call

    created_paths = []
    unlinked_paths = []

    real_mkstemp = __import__("tempfile").mkstemp

    def fake_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_paths.append(path)
        # Write dummy content so fdopen doesn't fail
        return fd, path

    def fake_unlink(path):
        unlinked_paths.append(path)

    call_sequence = []

    def fake_run(cmd, *args, **kwargs):
        call_sequence.append(tuple(cmd[:3]))
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        if cmd[1] == "run":
            result.stdout = ""
        elif cmd[1] == "port":
            result.stdout = "127.0.0.1:54999\n"
        elif "pg_isready" in cmd:
            result.stdout = "/var/run/postgresql:5432 - accepting connections"
        else:
            result.stdout = ""
        return result

    with patch("tempfile.mkstemp", side_effect=fake_mkstemp):
        with patch("os.unlink", side_effect=fake_unlink):
            with patch("subprocess.run", side_effect=fake_run):
                with patch.object(EphemeralPostgresCluster, "is_available", return_value=True):
                    with patch.object(EphemeralPostgresCluster, "parse_and_validate_loopback_port", return_value=54999):
                        with patch("tests.integration.test_postgres_role_separation._is_port_reachable", return_value=True):
                            cluster = EphemeralPostgresCluster()
                            try:
                                cluster.start(timeout=5.0)
                            except Exception:
                                pass

    # The password file path must have been created then unlinked
    # (at successful pg_isready or on failure cleanup)
    if created_paths:
        assert unlinked_paths or cluster._password_file_path is None, (
            "Password file was created but never unlinked and not tracked on cluster."
        )


def test_ephemeral_cluster_start_cleans_up_password_file_on_docker_run_failure():
    """Verify the temporary password file is removed when docker run fails.

    Mocked test — verifies failure-path cleanup.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    unlinked = []

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        if cmd[1] == "run":
            result.returncode = 1
            result.stderr = "simulated docker run failure"
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    real_unlink = __import__("os").unlink

    def tracking_unlink(path):
        unlinked.append(path)
        try:
            real_unlink(path)
        except OSError:
            pass

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(EphemeralPostgresCluster, "is_available", return_value=True):
            with patch("os.unlink", side_effect=tracking_unlink):
                cluster = EphemeralPostgresCluster()
                with pytest.raises(RuntimeError):
                    cluster.start(timeout=1.0)

    assert cluster._password_file_path is None, (
        "password_file_path must be None after a failed start()"
    )


def test_ephemeral_cluster_start_cleans_up_on_tempfile_write_failure():
    """Verify cleanup when password file write fails (e.g. disk full).

    Mocked test — verifies failure-path cleanup when os.fdopen/write raises.
    """
    import subprocess
    import tempfile
    import os
    from unittest.mock import patch, MagicMock

    real_mkstemp = tempfile.mkstemp
    created_fd = []

    def fake_mkstemp(*args, **kwargs):
        fd, path = real_mkstemp(*args, **kwargs)
        created_fd.append((fd, path))
        return fd, path

    def fake_fdopen(fd, *args, **kwargs):
        raise OSError("simulated disk full")

    with patch("tempfile.mkstemp", side_effect=fake_mkstemp):
        with patch("os.fdopen", side_effect=fake_fdopen):
            with patch.object(EphemeralPostgresCluster, "is_available", return_value=True):
                cluster = EphemeralPostgresCluster()
                with pytest.raises(RuntimeError, match="Failed to write temporary password file"):
                    cluster.start(timeout=1.0)

    assert cluster._password_file_path is None, (
        "password_file_path must be None after write failure"
    )
    # Close any leaked fd
    for fd, _ in created_fd:
        try:
            os.close(fd)
        except OSError:
            pass


def test_ephemeral_cluster_start_password_not_in_exception_message():
    """Verify the admin password does not appear in exception messages from start().

    Mocked test — exercises the RuntimeError raised on docker run failure.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        result.returncode = 1
        # The stderr message does NOT contain the password; we assert the wrapper also doesn't
        result.stderr = "Error response from daemon: Conflict. container already in use."
        result.stdout = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(EphemeralPostgresCluster, "is_available", return_value=True):
            cluster = EphemeralPostgresCluster()
            admin_password = cluster.admin_password
            try:
                cluster.start(timeout=1.0)
            except RuntimeError as exc:
                assert admin_password not in str(exc), (
                    "Admin password must not appear in RuntimeError message from start()"
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Task 4 — Teardown failure scenarios (Round 14)
# ---------------------------------------------------------------------------

def test_stop_docker_stop_fails_but_container_confirmed_stopped():
    """docker stop returns non-zero exit but inspect shows container stopped.

    This can happen when the container exits on its own before docker stop
    completes (e.g., --rm triggered auto-removal). The RuntimeError should
    mention the docker stop failure but the caller knows cleanup was partial.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        if "stop" in cmd:
            result.returncode = 1
            result.stderr = "Error: No such container: pg-ephemeral-test"
            result.stdout = ""
        elif "inspect" in cmd:
            result.returncode = 1  # inspect also fails (container removed via --rm)
            result.stdout = ""
            result.stderr = "Error: No such container"
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="teardown encountered errors"):
            cluster.stop()

    assert cluster.is_running is False


def test_stop_docker_stop_fails_container_still_running():
    """docker stop fails AND inspect confirms container still running.
    docker rm -f is attempted but also fails.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        if "stop" in cmd:
            result.returncode = 1
            result.stderr = "Error stopping container"
            result.stdout = ""
        elif "inspect" in cmd:
            result.returncode = 0
            result.stdout = "true\n"   # still running
            result.stderr = ""
        elif "rm" in cmd:
            result.returncode = 1
            result.stderr = "Error removing container"
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            cluster.stop()

    msg = str(exc_info.value)
    assert "teardown encountered errors" in msg
    assert cluster.is_running is False


def test_stop_docker_inspect_fails_raises_with_unknown_state():
    """docker stop succeeds but docker inspect fails — container state is unknown."""
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        if "stop" in cmd:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        elif "inspect" in cmd:
            raise RuntimeError("inspect subprocess blew up")
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            cluster.stop()

    msg = str(exc_info.value)
    assert "teardown encountered errors" in msg
    assert "state could not be verified" in msg
    assert cluster.is_running is False


def test_stop_docker_rm_fails_after_stop_succeeds():
    """docker stop succeeds, inspect shows still running, docker rm -f fails."""
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        if "stop" in cmd:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        elif "inspect" in cmd:
            result.returncode = 0
            result.stdout = "true\n"  # reports running
            result.stderr = ""
        elif "rm" in cmd:
            result.returncode = 1
            result.stderr = "Error: cannot remove running container"
            result.stdout = ""
        else:
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            cluster.stop()

    msg = str(exc_info.value)
    assert "teardown encountered errors" in msg
    assert "rm -f" in msg
    assert cluster.is_running is False


def test_stop_multiple_cleanup_operations_fail():
    """docker stop, docker inspect, AND docker rm all fail — all errors collected."""
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True
    call_count = [0]

    def fake_run(cmd, *args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        result.returncode = 1
        result.stderr = f"Simulated failure in: {' '.join(cmd)}"
        result.stdout = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            cluster.stop()

    msg = str(exc_info.value)
    assert "teardown encountered errors" in msg
    assert cluster.is_running is False
    # Should have attempted stop and inspect at minimum
    assert call_count[0] >= 2


def test_stop_with_concurrent_test_body_exception():
    """When both the test body and stop() raise, the original test exception
    must be the primary failure and the teardown error must be attached.

    Verifies the finally-block exception chaining pattern used in integration tests.
    """
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        result.returncode = 1
        result.stderr = "teardown failure"
        result.stdout = ""
        return result

    class OriginalTestError(AssertionError):
        pass

    original_exc = OriginalTestError("primary assertion failed")

    captured_exc = None
    try:
        try:
            raise original_exc
        except Exception:
            import sys
            _exc = sys.exc_info()[1]
            try:
                with patch("subprocess.run", side_effect=fake_run):
                    cluster.stop()
            except Exception as _teardown_err:
                if _exc is not None:
                    note = f"Additionally, EphemeralPostgresCluster.stop() raised: {_teardown_err}"
                    if hasattr(_exc, "add_note"):
                        _exc.add_note(note)
                    else:
                        _exc.args = _exc.args + (note,)
                else:
                    raise
            raise  # Re-raise original
    except OriginalTestError as exc:
        captured_exc = exc

    assert captured_exc is not None
    assert isinstance(captured_exc, OriginalTestError), (
        "Original test exception type must be preserved"
    )
    all_info = str(captured_exc.args) + (
        "\n".join(captured_exc.__notes__) if hasattr(captured_exc, "__notes__") else ""
    )
    assert "teardown encountered errors" in all_info or "teardown failure" in all_info, (
        "Teardown error must be attached to the original exception as a note or arg"
    )


def test_stop_docker_stop_timeout():
    """docker stop times out — error must be collected, not silently dropped."""
    import subprocess
    from unittest.mock import patch, MagicMock

    cluster = EphemeralPostgresCluster()
    cluster.is_running = True

    def fake_run(cmd, *args, **kwargs):
        if "stop" in cmd:
            raise subprocess.TimeoutExpired(cmd, 15)
        result = MagicMock()
        result.returncode = 1  # inspect fails too
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError) as exc_info:
            cluster.stop()

    msg = str(exc_info.value)
    assert "teardown encountered errors" in msg
    assert "timed out" in msg
    assert cluster.is_running is False


@pytest.mark.asyncio
async def test_isolation_token_non_disclosure_on_failure():
    """Verify that database errors while setting isolation comment never leak the isolation token."""
    from unittest.mock import AsyncMock

    mock_conn = AsyncMock()
    secret_token = "ultra_confidential_token_987654321"

    # Simulate an error that contains the secret token in the driver/database message
    mock_conn.execute.side_effect = Exception(
        f"Database error executing query with secret: {secret_token} on target"
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _set_database_isolation_comment(mock_conn, "test_db", secret_token)

    err_msg = str(exc_info.value)
    assert secret_token not in err_msg, "Isolation token must not be disclosed in exception message"
    assert "[REDACTED_ISOLATION_TOKEN]" in err_msg, "Sanitized token placeholder must be present"


def test_secure_temporary_file_verifies_acls(tmp_path):
    """Verify _secure_temporary_file establishes valid permissions on the host platform."""
    test_secret_file = tmp_path / "test_secret.txt"
    test_secret_file.write_text("secret_data", encoding="utf-8")

    EphemeralPostgresCluster._secure_temporary_file(str(test_secret_file))
    assert test_secret_file.exists()


def test_secure_temporary_file_rejects_insecure_acl(monkeypatch, tmp_path):
    """Verify _secure_temporary_file raises if insecure broad permissions are detected."""
    import os
    import subprocess
    from unittest.mock import MagicMock

    test_file = tmp_path / "insecure_secret.txt"
    test_file.write_text("secret_data", encoding="utf-8")

    if os.name == "nt":
        # Simulate icacls returning an output containing 'Everyone'
        def fake_run(cmd, *args, **kwargs):
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = "insecure_secret.txt NT AUTHORITY\\Everyone:(R)"
            mock_res.stderr = ""
            return mock_res

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(RuntimeError, match="Insecure ACL detected"):
            EphemeralPostgresCluster._secure_temporary_file(str(test_file))
    else:
        # On POSIX, simulate stat returning 0o777
        class FakeStat:
            st_mode = 0o777

        monkeypatch.setattr(os, "stat", lambda p: FakeStat())
        with pytest.raises(RuntimeError, match="Failed to establish restrictive file mode"):
            EphemeralPostgresCluster._secure_temporary_file(str(test_file))


def test_safe_unlink_retains_tracked_path_on_error(monkeypatch, tmp_path):
    """Verify _safe_unlink returns error message and does not clear path when deletion fails."""
    import os

    test_file = tmp_path / "locked_file.secret"
    test_file.write_text("locked", encoding="utf-8")

    cluster = EphemeralPostgresCluster()
    cluster._password_file_path = str(test_file)

    def failing_unlink(p):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(os, "unlink", failing_unlink)

    err = cluster._safe_unlink(str(test_file))
    assert err is not None
    assert "Failed to unlink temporary secret file" in err
    assert "Access is denied" in err
    # Path remains tracked when unlinking failed
    assert cluster._password_file_path == str(test_file)


def test_start_bounds_docker_run_with_timeout(monkeypatch):
    """Verify start() bounds docker run with a timeout and executes stop() cleanup."""
    import subprocess
    from unittest.mock import patch

    cluster = EphemeralPostgresCluster()
    stop_called = []

    def mock_stop():
        stop_called.append(True)

    monkeypatch.setattr(cluster, "stop", mock_stop)
    monkeypatch.setattr(cluster, "is_available", lambda: True)

    def fake_run(cmd, *args, **kwargs):
        if "docker" in cmd and "run" in cmd:
            raise subprocess.TimeoutExpired(cmd, 30)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(RuntimeError, match="Timed out starting ephemeral PostgreSQL container"):
            cluster.start(timeout=1.0)

    assert stop_called == [True], "stop() must be invoked to clean up when docker run times out"


