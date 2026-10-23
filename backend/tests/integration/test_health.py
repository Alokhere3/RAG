"""Integration tests for application startup and health endpoints."""

from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.endpoints.health import get_health_service
from app.services.health import HealthService


def test_application_starts(client: TestClient):
    """Test 001: Backend starts and responds."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint(client: TestClient):
    """Test 002: Health endpoint returns status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_endpoint(client: TestClient):
    """Test 003: Liveness endpoint returns status ok independently of dependencies."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_healthy(client: TestClient):
    """Readiness reports ready when both PostgreSQL and Redis are available."""
    mock_service = AsyncMock(spec=HealthService)
    mock_service.get_readiness.return_value = {
        "status": "ready",
        "dependencies": {"database": "ok", "redis": "ok"},
    }

    app.dependency_overrides[get_health_service] = lambda: mock_service
    try:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "dependencies": {"database": "ok", "redis": "ok"},
        }
    finally:
        app.dependency_overrides.clear()


def test_readiness_database_down(client: TestClient):
    """Test 004: Readiness endpoint reports not_ready when PostgreSQL is unavailable."""
    mock_service = AsyncMock(spec=HealthService)
    mock_service.get_readiness.return_value = {
        "status": "not_ready",
        "dependencies": {"database": "unavailable", "redis": "ok"},
    }

    app.dependency_overrides[get_health_service] = lambda: mock_service
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "dependencies": {"database": "unavailable", "redis": "ok"},
        }
    finally:
        app.dependency_overrides.clear()


def test_readiness_redis_down(client: TestClient):
    """Test 005: Readiness endpoint reports not_ready when Redis is unavailable."""
    mock_service = AsyncMock(spec=HealthService)
    mock_service.get_readiness.return_value = {
        "status": "not_ready",
        "dependencies": {"database": "ok", "redis": "unavailable"},
    }

    app.dependency_overrides[get_health_service] = lambda: mock_service
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "not_ready",
            "dependencies": {"database": "ok", "redis": "unavailable"},
        }
    finally:
        app.dependency_overrides.clear()


def test_api_v1_versioned_health(client: TestClient):
    """Verify health endpoints accessible under /api/v1 prefix."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_tracing_header(client: TestClient):
    """Verify X-Request-ID is generated and returned in headers."""
    response = client.get("/health")
    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) > 0

    # Test propagation of incoming header
    custom_id = "test-req-trace-12345"
    response_propagated = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response_propagated.headers.get("x-request-id") == custom_id
