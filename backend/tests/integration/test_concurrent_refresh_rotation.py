"""Integration tests verifying atomic refresh token rotation under concurrency (F-09)."""

import asyncio
from pathlib import Path
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.token import RefreshToken
from app.models.user import User, UserRole
from app.services.auth.sessions import create_refresh_session, rotate_refresh_token
from app.services.auth.tokens import InvalidTokenError, generate_refresh_token


@pytest.fixture
async def async_session_factory(tmp_path: Path):
    """Create a temporary SQLite async database session factory."""
    db_file = tmp_path / "test_concurrent_session.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file.as_posix()}",
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_refresh_rotation_prevents_dual_issuance(async_session_factory):
    """When two concurrent requests attempt to rotate the same refresh token, exactly one succeeds."""
    # Setup initial user and refresh token
    async with async_session_factory() as session:
        user = User(
            email="concurrent_test@company.local",
            password_hash="mock_hash",
            role=UserRole.USER,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

        raw_initial = generate_refresh_token()
        await create_refresh_session(session, user_id, raw_initial)
        await session.commit()

    results = []
    errors = []

    async def attempt_rotation(call_index: int):
        new_raw = generate_refresh_token()
        async with async_session_factory() as session:
            try:
                old_tok, new_tok = await rotate_refresh_token(
                    session=session,
                    raw_token=raw_initial,
                    new_raw_token=new_raw,
                    user_agent=f"ConcurrentClient-{call_index}",
                )
                results.append((call_index, new_tok.id))
            except InvalidTokenError as exc:
                errors.append((call_index, str(exc)))

    # Run both rotation requests concurrently
    await asyncio.gather(
        attempt_rotation(1),
        attempt_rotation(2),
        return_exceptions=True,
    )

    # Exactly one request must succeed, and the other must be rejected
    assert len(results) == 1, f"Expected exactly 1 successful rotation, got {len(results)}: {results}"
    assert len(errors) == 1, f"Expected exactly 1 rejected rotation, got {len(errors)}: {errors}"
    assert "reuse detected" in errors[0][1].lower() or "not found" in errors[0][1].lower()

    # Verify database state has exactly one replacement recorded
    async with async_session_factory() as session:
        stmt = select(RefreshToken).where(RefreshToken.user_id == user_id)
        res = await session.execute(stmt)
        all_tokens = res.scalars().all()
        # Initial token is revoked
        initial_token = next(t for t in all_tokens if t.replaced_by_token_id is not None)
        assert initial_token.is_revoked is True
        assert initial_token.replaced_by_token_id == results[0][1]
