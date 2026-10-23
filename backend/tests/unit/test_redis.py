"""Unit and integration tests for Redis infrastructure layer."""

from unittest.mock import AsyncMock, patch
import pytest
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.redis import (
    check_redis_connectivity,
    close_redis,
    get_redis,
)


@pytest.mark.asyncio
async def test_redis_settings_configuration():
    """Verify REDIS_URL configuration is loaded from settings."""
    settings = get_settings()
    assert settings.redis_url.startswith(("redis://", "rediss://"))


@pytest.mark.asyncio
async def test_redis_client_lazy_initialization_and_singleton():
    """Verify get_redis initializes lazily and reuses singleton instance."""
    await close_redis()
    client1 = get_redis()
    assert isinstance(client1, aioredis.Redis)
    client2 = get_redis()
    assert client1 is client2
    await close_redis()


@pytest.mark.asyncio
async def test_check_redis_connectivity_mock_success():
    """Verify check_redis_connectivity returns True on successful PING."""
    mock_client = AsyncMock(spec=aioredis.Redis)
    mock_client.ping = AsyncMock(return_value=True)

    with patch("app.core.redis.get_redis", return_value=mock_client):
        result = await check_redis_connectivity()
        assert result is True
        mock_client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_redis_connectivity_mock_failure():
    """Verify check_redis_connectivity returns False when PING fails or times out."""
    mock_client = AsyncMock(spec=aioredis.Redis)
    mock_client.ping = AsyncMock(side_effect=aioredis.ConnectionError("Connection refused"))

    with patch("app.core.redis.get_redis", return_value=mock_client):
        result = await check_redis_connectivity()
        assert result is False


@pytest.mark.asyncio
async def test_check_redis_connectivity_unreachable_network():
    """Verify check_redis_connectivity handles unreachable port without crashing."""
    unreachable_url = "redis://127.0.0.1:59998/0"
    result = await check_redis_connectivity(redis_url=unreachable_url, timeout=0.5)
    assert result is False


@pytest.mark.asyncio
async def test_close_redis():
    """Verify close_redis releases resources and resets singleton."""
    client = get_redis()
    assert client is not None
    await close_redis()

    import app.core.redis as redis_module
    assert redis_module._redis_client is None


@pytest.mark.asyncio
async def test_live_redis_ping_if_available():
    """Integration check: test real Redis PING if a server is reachable locally."""
    # Attempt probe against configured Redis URL with a short timeout
    is_live = await check_redis_connectivity(timeout=0.3)
    if is_live:
        client = get_redis()
        pong = await client.ping()
        assert pong is True
    else:
        # Pass gracefully when running without background Redis daemon
        assert is_live is False
