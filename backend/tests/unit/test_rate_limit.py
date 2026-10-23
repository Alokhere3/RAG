"""Tests for Redis-backed login throttling with resilient bounded fallback (F-08)."""

import logging
import pytest

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.services.auth import rate_limit


@pytest.fixture(autouse=True)
def clean_rate_limit_store():
    """Ensure in-memory fallback store is reset before and after each test."""
    rate_limit._clear_in_memory_rate_limits()
    yield
    rate_limit._clear_in_memory_rate_limits()


@pytest.mark.asyncio
async def test_login_rate_limit_rejects_after_configured_attempts(monkeypatch):
    """When Redis is operational, rate limit is enforced by Redis count."""
    settings = get_settings()
    monkeypatch.setattr(
        rate_limit,
        "increment_with_expiry",
        lambda *_args: _value(settings.login_rate_limit_attempts + 1),
    )
    with pytest.raises(AuthenticationError) as exc_info:
        await rate_limit.enforce_login_rate_limit("127.0.0.1", "user@example.com")
    assert exc_info.value.code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_login_rate_limit_falls_back_to_in_memory_when_redis_fails(monkeypatch, caplog):
    """When Redis is unavailable, rate limiting falls back to bounded in-memory counter."""
    settings = get_settings()

    async def redis_down(*_args):
        raise ConnectionError("Connection refused to redis:6379")

    monkeypatch.setattr(rate_limit, "increment_with_expiry", redis_down)

    with caplog.at_level(logging.WARNING):
        # Attempts up to limit should succeed without raising
        for _ in range(settings.login_rate_limit_attempts):
            await rate_limit.enforce_login_rate_limit("192.168.1.100", "test@company.com")

        # Exceeding the limit must trigger AuthenticationError (fail-closed/bounded)
        with pytest.raises(AuthenticationError) as exc_info:
            await rate_limit.enforce_login_rate_limit("192.168.1.100", "test@company.com")
        assert exc_info.value.code == "RATE_LIMITED"

    # Verify no raw exception traceback is leaked into logs
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("LOGIN_RATE_LIMIT_REDIS_UNAVAILABLE" in r.getMessage() for r in warning_records)
    assert not any("Traceback" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_in_memory_fallback_capacity_bound(monkeypatch):
    """Ensure in-memory store bounds memory growth under heavy load."""
    monkeypatch.setattr(rate_limit, "_MAX_IN_MEMORY_KEYS", 5)

    async def redis_down(*_args):
        raise ConnectionError("redis down")

    monkeypatch.setattr(rate_limit, "increment_with_expiry", redis_down)

    # Insert 10 different IP/email combinations
    for i in range(10):
        await rate_limit.enforce_login_rate_limit(f"10.0.0.{i}", f"user{i}@example.com")

    # Store must not exceed the bounded maximum
    with rate_limit._store_lock:
        assert len(rate_limit._in_memory_store) <= 5


async def _value(value: int) -> int:
    return value
