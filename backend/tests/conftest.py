"""Shared pytest fixtures."""

import os

# Explicit test harness configuration: ensure APP_ENV is explicitly set to testing
# before any application modules or settings are loaded.
os.environ.setdefault("APP_ENV", "testing")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import Settings, get_settings



@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def custom_settings() -> Settings:
    """Fixture providing clean settings for testing."""
    return get_settings()


@pytest.fixture(autouse=True)
def reset_rate_limit_store():
    """Reset the in-memory fallback rate limiter store between test executions."""
    from app.services.auth.rate_limit import _clear_in_memory_rate_limits

    _clear_in_memory_rate_limits()
    yield
    _clear_in_memory_rate_limits()

