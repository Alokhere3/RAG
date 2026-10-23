"""End-to-End White-Label Verification Tests (Chunk 1.8).

Verifies dynamic white-label switching between Configuration A and Configuration B
without code modifications, ensuring full property propagation and zero secret leakage.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Ensure clean cached settings between test runs."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_configuration_a_verification(monkeypatch):
    """Configuration A: Acme Corporation / Acme Knowledge Assistant / #123456."""
    config_a_env = {
        "APP_ENV": "development",
        "ORGANIZATION_NAME": "Acme Corporation",
        "ORGANIZATION_LOGO_URL": "https://assets.acme.com/logo.svg",
        "ORGANIZATION_WEBSITE_URL": "https://acme.com",
        "ASSISTANT_NAME": "Acme Knowledge Assistant",
        "ASSISTANT_DESCRIPTION": "Acme knowledge base virtual guide.",
        "ASSISTANT_AVATAR_URL": "https://assets.acme.com/avatar.png",
        "PRIMARY_COLOR": "#123456",
        "SECONDARY_COLOR": "#222222",
        "ACCENT_COLOR": "#333333",
        "FAVICON_URL": "https://assets.acme.com/favicon.ico",
        "ENABLE_CHAT": "true",
        "ENABLE_DOCUMENTS": "false",
        "DATABASE_URL": "postgresql+asyncpg://acme:secretpass@postgres:5432/acme_db",
        "REDIS_URL": "redis://:redissecret@redis:6379/1",
        "JWT_SECRET": "acme-super-secret-production-signing-key-32chars",
        "OPENAI_API_KEY": "sk-acme-fake-test-key-should-never-leak",
    }
    for key, value in config_a_env.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/api/v1/config")
    assert response.status_code == 200
    data = response.json()

    # Verify Configuration A branding
    assert data["organization"]["name"] == "Acme Corporation"
    assert data["organization"]["logoUrl"] == "https://assets.acme.com/logo.svg"
    assert data["organization"]["websiteUrl"] == "https://acme.com"

    assert data["assistant"]["name"] == "Acme Knowledge Assistant"
    assert data["assistant"]["description"] == "Acme knowledge base virtual guide."
    assert data["assistant"]["avatarUrl"] == "https://assets.acme.com/avatar.png"

    assert data["branding"]["primaryColor"] == "#123456"
    assert data["branding"]["secondaryColor"] == "#222222"
    assert data["branding"]["accentColor"] == "#333333"
    assert data["branding"]["faviconUrl"] == "https://assets.acme.com/favicon.ico"

    assert data["features"]["chat"] is True
    assert data["features"]["documents"] is False

    # Security check: Zero secrets in payload
    content_str = response.text.lower()
    for secret in ["secretpass", "redissecret", "signing-key", "sk-acme", "acme_db"]:
        assert secret not in content_str


def test_configuration_b_verification(monkeypatch):
    """Configuration B: Example University / University Knowledge Assistant / #654321.

    Tests dynamic rebranding without code modifications.
    """
    config_b_env = {
        "APP_ENV": "development",
        "ORGANIZATION_NAME": "Example University",
        "ORGANIZATION_LOGO_URL": "https://uni.edu/assets/crest.svg",
        "ORGANIZATION_WEBSITE_URL": "https://uni.edu",
        "ASSISTANT_NAME": "University Knowledge Assistant",
        "ASSISTANT_DESCRIPTION": "Campus directory and academic regulations advisor.",
        "ASSISTANT_AVATAR_URL": "https://uni.edu/assets/mascot.png",
        "PRIMARY_COLOR": "#654321",
        "SECONDARY_COLOR": "#444444",
        "ACCENT_COLOR": "#888888",
        "FAVICON_URL": "https://uni.edu/assets/favicon.ico",
        "ENABLE_CHAT": "false",
        "ENABLE_DOCUMENTS": "true",
        "DATABASE_URL": "postgresql+asyncpg://uni:unipassword@postgres:5432/uni_db",
        "REDIS_URL": "redis://:uniredis@redis:6379/2",
        "JWT_SECRET": "uni-super-secret-production-signing-key-32chars",
        "GEMINI_API_KEY": "AIzaSyFakeUniversitySecretKeyShouldNotLeak",
    }
    for key, value in config_b_env.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/api/v1/config")
    assert response.status_code == 200
    data = response.json()

    # Verify Configuration B branding
    assert data["organization"]["name"] == "Example University"
    assert data["organization"]["logoUrl"] == "https://uni.edu/assets/crest.svg"
    assert data["organization"]["websiteUrl"] == "https://uni.edu"

    assert data["assistant"]["name"] == "University Knowledge Assistant"
    assert data["assistant"]["description"] == "Campus directory and academic regulations advisor."
    assert data["assistant"]["avatarUrl"] == "https://uni.edu/assets/mascot.png"

    assert data["branding"]["primaryColor"] == "#654321"
    assert data["branding"]["secondaryColor"] == "#444444"
    assert data["branding"]["accentColor"] == "#888888"
    assert data["branding"]["faviconUrl"] == "https://uni.edu/assets/favicon.ico"

    assert data["features"]["chat"] is False
    assert data["features"]["documents"] is True

    # Security check: Zero secrets in payload
    content_str = response.text.lower()
    for secret in ["unipassword", "uniredis", "signing-key", "aizasy", "uni_db"]:
        assert secret not in content_str


def test_verification_matrix_private_setting_isolation(monkeypatch):
    """Verify that changing DB, Redis, or API keys does NOT impact public configuration."""
    base_env = {
        "ORGANIZATION_NAME": "Acme Corp",
        "DATABASE_URL": "postgresql+asyncpg://admin:super_secret_db_pass@db.internal:5432/rag_prod",
        "REDIS_URL": "redis://:super_secret_redis_pass@redis.internal:6379/0",
        "JWT_SECRET": "jwt-super-secret-key-that-must-never-be-exposed",
        "OPENAI_API_KEY": "sk-proj-super-secret-llm-token",
    }
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/api/v1/config")
    assert response.status_code == 200
    data = response.json()

    # Public config intact
    assert data["organization"]["name"] == "Acme Corp"

    # Infrastructure strings are completely absent
    res_text = response.text
    assert "super_secret_db_pass" not in res_text
    assert "super_secret_redis_pass" not in res_text
    assert "jwt-super-secret" not in res_text
    assert "sk-proj" not in res_text
    assert "db.internal" not in res_text
    assert "redis.internal" not in res_text
