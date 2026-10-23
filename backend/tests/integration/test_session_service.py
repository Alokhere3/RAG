"""Integration tests for refresh token session management, rotation, revocation, and reuse detection."""

from datetime import timedelta
from pathlib import Path
import uuid
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.user import User, UserRole
from app.models.token import RefreshToken
from app.services.auth.sessions import (
    create_refresh_session,
    revoke_all_user_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.auth.tokens import (
    ExpiredTokenError,
    InvalidTokenError,
    generate_refresh_token,
)


@pytest.fixture
async def async_session(tmp_path: Path):
    """Create a temporary SQLite async database session fixture."""
    db_file = tmp_path / "test_session_service.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    # Enable SQLite foreign keys
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_session_creation(async_session: AsyncSession):
    """Verify refresh token session is persisted with hash and valid expiration."""
    user = User(
        email="session_user@company.local",
        password_hash="mock_hash",
        role=UserRole.USER,
    )
    async_session.add(user)
    await async_session.commit()

    raw_token = generate_refresh_token()
    token_record = await create_refresh_session(
        session=async_session,
        user_id=user.id,
        raw_token=raw_token,
        user_agent="Mozilla/5.0 TestBrowser",
        ip_address="127.0.0.1",
    )
    await async_session.commit()

    assert token_record.id is not None
    assert token_record.user_id == user.id
    assert raw_token not in token_record.token_hash
    assert len(token_record.token_hash) == 64
    assert token_record.is_active is True
    assert token_record.is_revoked is False
    assert token_record.user_agent == "Mozilla/5.0 TestBrowser"
    assert token_record.ip_address == "127.0.0.1"


@pytest.mark.asyncio
async def test_refresh_token_rotation_success(async_session: AsyncSession):
    """Verify refresh rotation revokes old token and issues linked new token."""
    user = User(
        email="rotate_user@company.local",
        password_hash="mock_hash",
    )
    async_session.add(user)
    await async_session.commit()

    old_raw = generate_refresh_token()
    old_record = await create_refresh_session(async_session, user.id, old_raw)
    await async_session.commit()

    # Rotate
    new_raw = generate_refresh_token()
    old_rotated, new_rotated = await rotate_refresh_token(
        session=async_session,
        raw_token=old_raw,
        new_raw_token=new_raw,
        user_agent="Updated Browser",
        ip_address="192.168.1.1",
    )

    assert old_rotated.id == old_record.id
    assert old_rotated.is_revoked is True
    assert old_rotated.revoked_at is not None
    assert old_rotated.replaced_by_token_id == new_rotated.id

    assert new_rotated.is_active is True
    assert new_rotated.user_id == user.id
    assert new_rotated.user_agent == "Updated Browser"


@pytest.mark.asyncio
async def test_refresh_rotation_reuse_theft_detection(async_session: AsyncSession):
    """Verify that reusing an already revoked refresh token invalidates all user sessions."""
    user = User(
        email="theft_victim@company.local",
        password_hash="mock_hash",
    )
    async_session.add(user)
    await async_session.commit()

    token_raw_1 = generate_refresh_token()
    await create_refresh_session(async_session, user.id, token_raw_1)
    await async_session.commit()

    # Legitimate rotation from token 1 to token 2
    token_raw_2 = generate_refresh_token()
    await rotate_refresh_token(async_session, token_raw_1, token_raw_2)

    # Also simulate another active session on another device (token 3)
    token_raw_3 = generate_refresh_token()
    token_record_3 = await create_refresh_session(async_session, user.id, token_raw_3)
    await async_session.commit()
    assert token_record_3.is_active is True

    # Attacker tries to reuse token 1 (already revoked!)
    token_raw_attacker = generate_refresh_token()
    with pytest.raises(InvalidTokenError) as exc_info:
        await rotate_refresh_token(async_session, token_raw_1, token_raw_attacker)
    assert "reuse detected" in str(exc_info.value).lower()

    # Verify that token 3 (and ALL sessions for this user) was revoked as theft mitigation!
    await async_session.refresh(token_record_3)
    assert token_record_3.is_revoked is True


@pytest.mark.asyncio
async def test_refresh_token_revocation_on_logout(async_session: AsyncSession):
    """Verify explicit revocation marks token as revoked."""
    user = User(
        email="logout_user@company.local",
        password_hash="mock_hash",
    )
    async_session.add(user)
    await async_session.commit()

    raw_token = generate_refresh_token()
    token_record = await create_refresh_session(async_session, user.id, raw_token)
    await async_session.commit()

    # Revoke
    revoked = await revoke_refresh_token(async_session, raw_token)
    assert revoked is True

    await async_session.refresh(token_record)
    assert token_record.is_revoked is True

    # Revoking again returns False (idempotent)
    assert await revoke_refresh_token(async_session, raw_token) is False


@pytest.mark.asyncio
async def test_expired_refresh_token_rotation_rejected(async_session: AsyncSession):
    """Verify expired refresh tokens are rejected during rotation without reuse alert."""
    user = User(
        email="expired_user@company.local",
        password_hash="mock_hash",
    )
    async_session.add(user)
    await async_session.commit()

    raw_token = generate_refresh_token()
    # Create token expired 1 day ago
    await create_refresh_session(
        async_session,
        user.id,
        raw_token,
        expires_delta=timedelta(days=-1),
    )
    await async_session.commit()

    new_raw = generate_refresh_token()
    with pytest.raises(ExpiredTokenError):
        await rotate_refresh_token(async_session, raw_token, new_raw)
