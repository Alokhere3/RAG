"""Unit test verifying Docker Compose network, port isolation, and production hardening (F-06, F-07, F-12B)."""

from pathlib import Path
import yaml


def _load_compose():
    """Load and return parsed docker-compose.yml."""
    compose_path = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml not found at {compose_path}"
    with open(compose_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_docker_compose_ports_bind_to_loopback():
    """Verify that all exposed ports in docker-compose.yml bind strictly to 127.0.0.1."""
    compose_data = _load_compose()
    services = compose_data.get("services", {})
    assert len(services) > 0, "No services found in docker-compose.yml"

    for service_name, service_config in services.items():
        ports = service_config.get("ports", [])
        for port_mapping in ports:
            # Each mapping should start with "127.0.0.1:"
            assert str(port_mapping).startswith("127.0.0.1:"), (
                f"Service '{service_name}' exposes port '{port_mapping}' without binding to 127.0.0.1. "
                "All published ports must bind strictly to loopback (127.0.0.1) to enforce TLS edge termination."
            )


def test_docker_compose_migrations_default_false():
    """Verify RUN_MIGRATIONS_ON_STARTUP defaults to false in docker-compose.yml (F-12B)."""
    compose_data = _load_compose()
    backend_env = compose_data["services"]["backend"]["environment"]
    migration_val = backend_env.get("RUN_MIGRATIONS_ON_STARTUP", "")
    assert "false" in str(migration_val).lower(), (
        f"RUN_MIGRATIONS_ON_STARTUP should default to false in docker-compose.yml, "
        f"got: {migration_val}"
    )


def test_docker_compose_redis_url_parameterized():
    """Verify REDIS_URL is parameterized (not hardcoded) in backend and worker (F-07)."""
    compose_data = _load_compose()
    for svc_name in ("backend", "worker"):
        svc_env = compose_data["services"][svc_name]["environment"]
        redis_url = str(svc_env.get("REDIS_URL", ""))
        # Should contain ${REDIS_URL:- or similar variable substitution
        assert "${REDIS_URL" in redis_url or "redis://" in redis_url, (
            f"Service '{svc_name}' REDIS_URL should be parameterized, got: {redis_url}"
        )
        # Must NOT be a bare hardcoded value without variable substitution
        assert redis_url != "redis://redis:6379/0", (
            f"Service '{svc_name}' REDIS_URL is hardcoded without variable substitution. "
            "Use ${{REDIS_URL:-redis://redis:6379/0}} to allow operator override (F-07)."
        )


def test_docker_compose_redis_supports_auth():
    """Verify Redis service supports password authentication via REDIS_PASSWORD (F-07)."""
    compose_data = _load_compose()
    redis_svc = compose_data["services"]["redis"]

    # Redis should have a command that references REDIS_PASSWORD / requirepass
    command = str(redis_svc.get("command", ""))
    assert "requirepass" in command, (
        "Redis service 'command' should support --requirepass for password authentication (F-07)."
    )

    # Redis should have REDIS_PASSWORD in its environment
    redis_env = redis_svc.get("environment", {})
    assert "REDIS_PASSWORD" in redis_env, (
        "Redis service should pass REDIS_PASSWORD environment variable (F-07)."
    )


def test_docker_compose_init_roles_mounted():
    """Verify init-roles.sql is mounted in postgres service (F-12B)."""
    compose_data = _load_compose()
    pg_volumes = compose_data["services"]["postgres"].get("volumes", [])
    volume_strs = [str(v) for v in pg_volumes]
    assert any("init-roles.sql" in v for v in volume_strs), (
        "Postgres service must mount init-roles.sql for role separation (F-12B). "
        f"Found volumes: {volume_strs}"
    )


def test_docker_compose_migration_database_url_exists():
    """Verify MIGRATION_DATABASE_URL is passed to backend service (F-12B)."""
    compose_data = _load_compose()
    backend_env = compose_data["services"]["backend"]["environment"]
    assert "MIGRATION_DATABASE_URL" in backend_env, (
        "Backend service must have MIGRATION_DATABASE_URL environment variable for role separation (F-12B)."
    )


def test_docker_compose_app_env_fails_closed():
    """Verify APP_ENV requires explicit definition and does not silently default to development."""
    compose_data = _load_compose()
    for svc in ("backend", "worker"):
        app_env = str(compose_data["services"][svc]["environment"].get("APP_ENV", ""))
        assert ":?" in app_env, (
            f"Service '{svc}' APP_ENV must fail closed (use ${{APP_ENV:?err_msg}}), got: {app_env}"
        )
        assert "development" not in app_env or "e.g." in app_env, (
            f"Service '{svc}' APP_ENV should not provide an implicit fallback to development"
        )


def test_docker_compose_auth_cookie_secure_does_not_force_false():
    """Verify AUTH_COOKIE_SECURE does not silently force insecure false default in Compose."""
    compose_data = _load_compose()
    backend_env = compose_data["services"]["backend"]["environment"]
    cookie_sec = str(backend_env.get("AUTH_COOKIE_SECURE", ""))
    assert ":-false" not in cookie_sec, (
        f"AUTH_COOKIE_SECURE in Compose forces :-false, got: {cookie_sec}. "
        "It must use ${{AUTH_COOKIE_SECURE:-}} to allow settings.py to default True in production."
    )


def test_docker_compose_database_url_uses_least_privilege_app_role():
    """Verify runtime DATABASE_URL in backend and worker uses rag_app, not POSTGRES_USER superuser."""
    compose_data = _load_compose()
    for svc in ("backend", "worker"):
        db_url = str(compose_data["services"][svc]["environment"].get("DATABASE_URL", ""))
        assert "rag_app" in db_url, (
            f"Service '{svc}' DATABASE_URL must default to rag_app role, got: {db_url}"
        )
        assert "POSTGRES_USER" not in db_url, (
            f"Service '{svc}' DATABASE_URL must not use POSTGRES_USER superuser credentials, got: {db_url}"
        )


def test_docker_compose_migration_database_url_uses_migrator_role():
    """Verify MIGRATION_DATABASE_URL in backend uses rag_migrator, not POSTGRES_USER superuser."""
    compose_data = _load_compose()
    mig_url = str(compose_data["services"]["backend"]["environment"].get("MIGRATION_DATABASE_URL", ""))
    assert "rag_migrator" in mig_url, (
        f"Backend MIGRATION_DATABASE_URL must default to rag_migrator role, got: {mig_url}"
    )
    assert "POSTGRES_USER" not in mig_url, (
        f"Backend MIGRATION_DATABASE_URL must not use POSTGRES_USER superuser credentials, got: {mig_url}"
    )


def test_docker_compose_postgres_password_fails_closed():
    """Verify POSTGRES_PASSWORD in postgres service requires explicit setting (no default)."""
    compose_data = _load_compose()
    pg_env = compose_data["services"]["postgres"]["environment"]
    pg_pass = str(pg_env.get("POSTGRES_PASSWORD", ""))
    assert ":?" in pg_pass, (
        f"POSTGRES_PASSWORD in postgres service must fail closed via :?, got: {pg_pass}"
    )


def test_docker_compose_role_passwords_fail_closed():
    """Verify RAG_APP_PASSWORD and RAG_MIGRATOR_PASSWORD require explicit setting in compose."""
    compose_data = _load_compose()
    pg_env = compose_data["services"]["postgres"]["environment"]
    for role_pass in ("RAG_APP_PASSWORD", "RAG_MIGRATOR_PASSWORD"):
        val = str(pg_env.get(role_pass, ""))
        assert ":?" in val, (
            f"{role_pass} in postgres service must fail closed via :?, got: {val}"
        )


def test_docker_compose_init_script_and_sql_mounted():
    """Verify 02-init-roles.sh and init-roles.sql are both mounted in postgres service."""
    compose_data = _load_compose()
    pg_volumes = [str(v) for v in compose_data["services"]["postgres"].get("volumes", [])]
    assert any("02-init-roles.sh" in v for v in pg_volumes), (
        f"Postgres service must mount 02-init-roles.sh for parameterized bootstrap. Volumes: {pg_volumes}"
    )
    assert any("init-roles.sql" in v for v in pg_volumes), (
        f"Postgres service must mount init-roles.sql. Volumes: {pg_volumes}"
    )


def test_docker_compose_rotation_scripts_mounted():
    """Verify rotate-role-passwords.sh and rotate-role-passwords.sql are mounted in postgres service."""
    compose_data = _load_compose()
    pg_volumes = [str(v) for v in compose_data["services"]["postgres"].get("volumes", [])]
    assert any("rotate-role-passwords.sh" in v for v in pg_volumes), (
        f"Postgres service must mount rotate-role-passwords.sh for credential rotation. Volumes: {pg_volumes}"
    )
    assert any("rotate-role-passwords.sql" in v for v in pg_volumes), (
        f"Postgres service must mount rotate-role-passwords.sql. Volumes: {pg_volumes}"
    )


def test_docker_compose_recovery_script_mounted():
    """Verify recover-initialization.sh is mounted in postgres service."""
    compose_data = _load_compose()
    pg_volumes = [str(v) for v in compose_data["services"]["postgres"].get("volumes", [])]
    assert any("recover-initialization.sh" in v for v in pg_volumes), (
        f"Postgres service must mount recover-initialization.sh for initialization recovery. Volumes: {pg_volumes}"
    )

