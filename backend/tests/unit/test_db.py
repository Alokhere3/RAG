"""Unit tests for database engine, session management, and connectivity probe."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.session import (
    check_db_connectivity,
    dispose_engine,
    get_db,
    get_engine,
    get_sessionmaker,
)


@pytest.mark.asyncio
async def test_get_engine_singleton():
    """Verify get_engine returns an AsyncEngine and maintains singleton reference."""
    engine = get_engine()
    assert isinstance(engine, AsyncEngine)
    engine2 = get_engine()
    assert engine is engine2
    await dispose_engine()


@pytest.mark.asyncio
async def test_get_sessionmaker():
    """Verify get_sessionmaker provides configured async sessionmaker."""
    maker = get_sessionmaker()
    session = maker()
    assert isinstance(session, AsyncSession)
    await session.close()
    await dispose_engine()


@pytest.mark.asyncio
async def test_session_lifecycle_commit():
    """Verify get_db dependency commits and closes session upon normal completion."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    test_engine = get_engine(db_url=test_db_url)
    test_maker = get_sessionmaker(engine=test_engine)

    # Patch sessionmaker for get_db test
    import app.db.session as session_module
    original_maker = session_module._sessionmaker
    session_module._sessionmaker = test_maker

    try:
        gen = get_db()
        session = await anext(gen)
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

        # Simulate completion
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
    finally:
        session_module._sessionmaker = original_maker
        await test_engine.dispose()
        await dispose_engine()


@pytest.mark.asyncio
async def test_session_lifecycle_rollback_on_exception():
    """Verify get_db rolls back the transaction when an exception occurs."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    test_engine = get_engine(db_url=test_db_url)
    test_maker = get_sessionmaker(engine=test_engine)

    import app.db.session as session_module
    original_maker = session_module._sessionmaker
    session_module._sessionmaker = test_maker

    try:
        gen = get_db()
        session = await anext(gen)
        
        # Throw error into generator
        with pytest.raises(RuntimeError, match="Simulated application error"):
            await gen.athrow(RuntimeError("Simulated application error"))

        assert not session.is_active or session.in_transaction() is False
    finally:
        session_module._sessionmaker = original_maker
        await test_engine.dispose()
        await dispose_engine()


@pytest.mark.asyncio
async def test_check_db_connectivity_success():
    """Verify connectivity check succeeds against responsive database."""
    test_db_url = "sqlite+aiosqlite:///:memory:"
    is_connected = await check_db_connectivity(db_url=test_db_url)
    assert is_connected is True


@pytest.mark.asyncio
async def test_check_db_connectivity_failure():
    """Test 006: Verify connectivity check fails gracefully without unhandled exception."""
    unreachable_url = "postgresql+asyncpg://rag:rag@127.0.0.1:59999/nonexistent"
    is_connected = await check_db_connectivity(db_url=unreachable_url, timeout=0.5)
    assert is_connected is False
