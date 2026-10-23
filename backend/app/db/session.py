"""Database Engine and Session Management.

Conforms to Phase 0 Chunk 0.3 requirements:
- SQLAlchemy 2.0 Async Engine and async_sessionmaker
- Sensible connection pooling (pool_pre_ping=True, pool_size=10, max_overflow=20)
- Lazy engine instantiation to prevent connection attempts at module import time
- Robust get_db() session dependency with commit/rollback/close lifecycle
- check_db_connectivity() probe for centralized health checking
"""

import asyncio
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import logger

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(db_url: str | None = None) -> AsyncEngine:
    """Return or lazily initialize the singleton AsyncEngine."""
    global _engine
    if _engine is None or db_url is not None:
        raw_url = db_url or get_settings().database_url
        target_url = raw_url.get_secret_value() if hasattr(raw_url, "get_secret_value") else str(raw_url)
        engine_kwargs = {
            "pool_pre_ping": True,
            "echo": get_settings().debug,
        }
        if not target_url.startswith("sqlite"):
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20

        new_engine = create_async_engine(target_url, **engine_kwargs)
        if db_url is None:
            _engine = new_engine
            return _engine
        return new_engine
    return _engine


def get_sessionmaker(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    """Return or lazily initialize the sessionmaker bound to the engine."""
    global _sessionmaker
    target_engine = engine or get_engine()
    if _sessionmaker is None or engine is not None:
        maker = async_sessionmaker(
            bind=target_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        if engine is None:
            _sessionmaker = maker
            return _sessionmaker
        return maker
    return _sessionmaker


def async_session_factory():
    """Callable returning a new AsyncSession from the default sessionmaker."""
    return get_sessionmaker()()


async def dispose_engine() -> None:
    """Explicitly close engine connection pools (e.g., during shutdown or tests)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an AsyncSession with automated transaction management."""
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_db_connectivity(db_url: str | None = None, timeout: float = 2.0) -> bool:
    """Verify database connectivity using a lightweight query."""
    engine = get_engine(db_url=db_url)
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=timeout)
        return True
    except Exception as e:
        logger.warning(f"Database connectivity probe failed: {str(e)}")
        return False
    finally:
        if db_url is not None:
            await engine.dispose()
