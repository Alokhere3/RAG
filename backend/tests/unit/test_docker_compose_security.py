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

