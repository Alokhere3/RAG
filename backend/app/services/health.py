"""Health Check Service.

Probes core application dependencies (PostgreSQL and Redis) with non-blocking timeouts
and clear status classification conforming to Section 7.
"""

import asyncio
from typing import Any, Literal

from app.core.config import get_settings
from app.core.logging import logger

DependencyStatus = Literal["ok", "unavailable"]


class HealthService:
    """Service to probe dependencies and report readiness."""

    def __init__(self, db_url: str | None = None, redis_url: str | None = None):
        settings = get_settings()
        raw_db = db_url or settings.database_url
        self.db_url = raw_db.get_secret_value() if hasattr(raw_db, "get_secret_value") else str(raw_db)
        raw_redis = redis_url or settings.redis_url
        self.redis_url = raw_redis.get_secret_value() if hasattr(raw_redis, "get_secret_value") else str(raw_redis)

    async def check_database(self, timeout: float = 2.0) -> DependencyStatus:
        """Probe PostgreSQL connection via centralized DB layer."""
        from app.db.session import check_db_connectivity
        is_connected = await check_db_connectivity(db_url=self.db_url, timeout=timeout)
        return "ok" if is_connected else "unavailable"

    async def check_redis(self, timeout: float = 2.0) -> DependencyStatus:
        """Probe Redis connection via centralized Redis layer."""
        from app.core.redis import check_redis_connectivity
        is_connected = await check_redis_connectivity(redis_url=self.redis_url, timeout=timeout)
        return "ok" if is_connected else "unavailable"

    async def get_readiness(self) -> dict[str, Any]:
        """Perform parallel checks and return overall readiness payload."""
        db_status, redis_status = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
        )

        all_ok = (db_status == "ok") and (redis_status == "ok")
        return {
            "status": "ready" if all_ok else "not_ready",
            "dependencies": {
                "database": db_status,
                "redis": redis_status,
            },
        }
