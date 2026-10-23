"""Redis Infrastructure Client.

Conforms to Phase 0 Chunk 0.4 requirements:
- Asynchronous Redis client via redis.asyncio
- Reusable singleton with lazy initialization
- Centralized configuration via app.core.config.get_settings()
- Non-blocking check_redis_connectivity() probe
- Safe lifecycle management with close_redis()
"""

import asyncio
from typing import Optional
import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.logging import logger

_redis_client: Optional[aioredis.Redis] = None


async def increment_with_expiry(key: str, window_seconds: int) -> int:
    """Atomically increment a counter and apply a TTL for rate limiting."""
    client = get_redis()
    count = int(await client.incr(key))
    if count == 1:
        await client.expire(key, window_seconds)
    return count


def get_redis(redis_url: Optional[str] = None) -> aioredis.Redis:
    """Return or lazily initialize the singleton async Redis client."""
    global _redis_client
    if _redis_client is None or redis_url is not None:
        raw_url = redis_url or get_settings().redis_url
        target_url = raw_url.get_secret_value() if hasattr(raw_url, "get_secret_value") else str(raw_url)
        client = aioredis.from_url(
            target_url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            decode_responses=False,
        )
        if redis_url is None:
            _redis_client = client
            return _redis_client
        return client
    return _redis_client


async def check_redis_connectivity(
    redis_url: Optional[str] = None, timeout: float = 2.0
) -> bool:
    """Probe Redis availability using an async PING command."""
    client = get_redis(redis_url=redis_url)
    try:
        response = await asyncio.wait_for(client.ping(), timeout=timeout)
        return bool(response)
    except Exception as e:
        logger.warning(f"Redis connectivity probe failed: {str(e)}")
        return False
    finally:
        if redis_url is not None:
            await client.aclose()


async def close_redis() -> None:
    """Gracefully close and release Redis client resources."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as e:
            logger.warning(f"Error closing Redis client: {str(e)}")
        finally:
            _redis_client = None
