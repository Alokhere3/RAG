"""Integration tests for GET /api/v1/config public configuration endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Test client fixture."""
    return TestClient(app)


def test_get_config_success_status_and_schema(client: TestClient):
    """Ensure GET /api/v1/config returns HTTP 200 and conforms to PublicConfigResponse."""
    response = client.get("/api/v1/config")
    assert response.status_code == 200

    data = response.json()

    # Validate top-level keys
    assert "application" in data
    assert "organization" in data
    assert "assistant" in data
    assert "branding" in data
    assert "features" in data

    # Validate application section
    assert isinstance(data["application"]["name"], str)
    assert isinstance(data["application"]["version"], str)
    assert isinstance(data["application"]["environment"], str)

    # Validate organization section (camelCase aliases)
    assert "name" in data["organization"]
    assert "logoUrl" in data["organization"]
    assert "websiteUrl" in data["organization"]

    # Validate assistant section (camelCase aliases)
    assert "name" in data["assistant"]
    assert "description" in data["assistant"]
    assert "avatarUrl" in data["assistant"]

    # Validate branding section (camelCase aliases)
    assert "primaryColor" in data["branding"]
    assert "secondaryColor" in data["branding"]
    assert "accentColor" in data["branding"]
    assert "faviconUrl" in data["branding"]
    assert data["branding"]["primaryColor"].startswith("#")

    # Validate features section
    assert isinstance(data["features"]["chat"], bool)
    assert isinstance(data["features"]["documents"], bool)


def test_get_config_security_boundary_no_secrets(client: TestClient):
    """Ensure no database passwords, Redis URLs, or server keys are exposed."""
    response = client.get("/api/v1/config")
    assert response.status_code == 200

    raw_text = response.text.lower()

    # Verify no private connection strings, driver schemes, or secret keys appear anywhere in response text
    forbidden_tokens = [
        "postgresql",
        "asyncpg",
        "redis://",
        "password",
        "jwt_secret",
        "openai_api_key",
        "gemini_api_key",
        "storage_bucket",
        "postgres_user",
        "postgres_db",
    ]

    for token in forbidden_tokens:
        assert token not in raw_text, f"Security violation: found '{token}' in public config response"


def test_get_config_dynamic_propagation(client: TestClient):
    """Ensure changes to application settings dynamically propagate to API output."""
    custom_settings = Settings(
        app_env="testing",
        app_name="Custom Enterprise Platform",
        app_version="2.0.0",
        organization_name="Global Logistics Inc",
        organization_logo_url="https://globallogistics.com/logo.svg",
        organization_website_url="https://globallogistics.com",
        assistant_name="Logistics Dispatcher",
        assistant_description="Handles global shipping inquiries",
        assistant_avatar_url="https://globallogistics.com/avatar.png",
        primary_color="#DC2626",
        secondary_color="#18181B",
        accent_color="#EF4444",
        favicon_url="https://globallogistics.com/favicon.ico",
        enable_chat=True,
        enable_documents=True,
        database_url="postgresql+asyncpg://user:pass@db:5432/db",
        redis_url="redis://redis:6379/0",
    )

    # Override get_settings dependency/cache
    app.dependency_overrides[get_settings] = lambda: custom_settings

    # Also temporarily mock get_settings in endpoints
    from unittest.mock import patch

    with patch("app.api.v1.endpoints.config.get_settings", return_value=custom_settings):
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()

        assert data["application"]["name"] == "Custom Enterprise Platform"
        assert data["application"]["version"] == "2.0.0"
        assert data["organization"]["name"] == "Global Logistics Inc"
        assert data["organization"]["logoUrl"] == "https://globallogistics.com/logo.svg"
        assert data["organization"]["websiteUrl"] == "https://globallogistics.com"
        assert data["assistant"]["name"] == "Logistics Dispatcher"
        assert data["assistant"]["description"] == "Handles global shipping inquiries"
        assert data["assistant"]["avatarUrl"] == "https://globallogistics.com/avatar.png"
        assert data["branding"]["primaryColor"] == "#DC2626"
        assert data["branding"]["secondaryColor"] == "#18181B"
        assert data["branding"]["accentColor"] == "#EF4444"
        assert data["branding"]["faviconUrl"] == "https://globallogistics.com/favicon.ico"
        assert data["features"]["chat"] is True
        assert data["features"]["documents"] is True

    app.dependency_overrides.clear()
