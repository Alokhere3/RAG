"""Login abuse protection with Redis backing and bounded in-memory fallback."""

import hashlib
import logging
import threading
import time
from typing import Tuple

from app.core.config import get_settings
from app.core.errors import AuthenticationError
from app.core.redis import increment_with_expiry

logger = logging.getLogger(__name__)

# Bounded in-memory fallback store to protect against Redis outages without memory exhaustion
_MAX_IN_MEMORY_KEYS = 10000
_in_memory_store: dict[str, Tuple[int, float]] = {}  # key -> (count, expiry_timestamp)
_store_lock = threading.Lock()


def _clear_in_memory_rate_limits() -> None:
    """Helper to reset in-memory fallback cache (primarily for tests)."""
    with _store_lock:
        _in_memory_store.clear()


def _increment_in_memory(key: str, window_seconds: int) -> int:
    """Thread-safe bounded in-memory counter with TTL and max size limits."""
    now = time.time()
    with _store_lock:
        # Periodic pruning if capacity is reached
        if len(_in_memory_store) >= _MAX_IN_MEMORY_KEYS:
            expired = [k for k, (_cnt, exp) in _in_memory_store.items() if exp <= now]
            for k in expired:
                del _in_memory_store[k]

            # If still over limit, evict the oldest entry
            if len(_in_memory_store) >= _MAX_IN_MEMORY_KEYS:
                oldest_key = min(_in_memory_store.keys(), key=lambda k: _in_memory_store[k][1])
                del _in_memory_store[oldest_key]

        if key in _in_memory_store:
            count, exp = _in_memory_store[key]
            if now < exp:
                new_count = count + 1
                _in_memory_store[key] = (new_count, exp)
                return new_count

        new_count = 1
        _in_memory_store[key] = (new_count, now + window_seconds)
        return new_count


def _key(ip_address: str | None, email: str) -> str:
    identity = f"{ip_address or 'unknown'}:{email}".encode("utf-8")
    return f"auth:login:{hashlib.sha256(identity).hexdigest()}"


async def enforce_login_rate_limit(ip_address: str | None, email: str) -> None:
    """Throttle repeated attempts; falls back safely to bounded in-memory limiter on Redis failure."""
    settings = get_settings()
    key = _key(ip_address, email)
    count: int

    try:
        count = await increment_with_expiry(key, settings.login_rate_limit_window_seconds)
    except Exception as exc:
        # Redact connection details and log clean security warning without stack trace
        logger.warning(
            "LOGIN_RATE_LIMIT_REDIS_UNAVAILABLE: Falling back to bounded in-memory limiter. Reason: %s",
            type(exc).__name__,
        )
        count = _increment_in_memory(key, settings.login_rate_limit_window_seconds)

    if count > settings.login_rate_limit_attempts:
        logger.warning("LOGIN_RATE_LIMITED ip=%s", ip_address)
        raise AuthenticationError(
            message="Too many login attempts. Try again later.",
            code="RATE_LIMITED",
        )

