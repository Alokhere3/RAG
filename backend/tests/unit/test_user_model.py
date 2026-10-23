"""Unit tests for User and RefreshToken ORM models and helpers."""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.user import User, UserRole, UserStatus, normalize_email
from app.models.token import RefreshToken


def test_normalize_email():
    """Verify email normalization handles whitespace, casing, and empty values."""
    assert normalize_email("  ALOK@EXAMPLE.COM  ") == "alok@example.com"
    assert normalize_email("Test.User+Tag@Domain.Org ") == "test.user+tag@domain.org"
    assert normalize_email("") == ""
    assert normalize_email("admin@platform.local") == "admin@platform.local"


def test_user_model_instantiation():
    """Verify User model initializes with defaults and normalizes email."""
    user = User(
        email="  Alice@Example.COM ",
        password_hash="argon2id_mock_hash",
        display_name="Alice Admin",
    )

    assert isinstance(user.id, uuid.UUID)
    assert user.email == "alice@example.com"
    assert user.password_hash == "argon2id_mock_hash"
    assert user.display_name == "Alice Admin"
    assert user.role == UserRole.USER
    assert user.status == UserStatus.ACTIVE


def test_refresh_token_active_properties():
    """Verify RefreshToken is_active, is_expired, and is_revoked properties."""
    user_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Valid token
    token = RefreshToken(
        user_id=user_id,
        token_hash="a" * 64,
        expires_at=now + timedelta(days=7),
    )
    assert isinstance(token.id, uuid.UUID)
    assert token.is_active is True
    assert token.is_expired is False
    assert token.is_revoked is False

    # Expired token
    expired_token = RefreshToken(
        user_id=user_id,
        token_hash="b" * 64,
        expires_at=now - timedelta(minutes=1),
    )
    assert expired_token.is_active is False
    assert expired_token.is_expired is True

    # Revoked token
    revoked_token = RefreshToken(
        user_id=user_id,
        token_hash="c" * 64,
        expires_at=now + timedelta(days=7),
        revoked_at=now,
    )
    assert revoked_token.is_active is False
    assert revoked_token.is_revoked is True


@pytest.mark.asyncio
async def test_user_persistence_and_unique_email(tmp_path):
    """Verify User database persistence, UUID generation, and unique email constraint."""
    db_file = tmp_path / "test_user_persistence.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        user1 = User(
            email="unique@example.com",
            password_hash="hashed_pw_1",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        session.add(user1)
        await session.commit()
        await session.refresh(user1)

        assert isinstance(user1.id, uuid.UUID)
        assert user1.email == "unique@example.com"
        assert user1.role == UserRole.ADMIN

    # Verify duplicate email violates unique constraint
    async with session_factory() as session:
        user_dup = User(
            email="UNIQUE@EXAMPLE.COM",  # normalizes to unique@example.com
            password_hash="hashed_pw_2",
        )
        session.add(user_dup)
        with pytest.raises(IntegrityError):
            await session.commit()

    await engine.dispose()


@pytest.mark.asyncio
async def test_user_refresh_token_cascade_delete(tmp_path):
    """Verify cascade deletion of refresh tokens when parent user is deleted."""
    db_file = tmp_path / "test_cascade.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    # Enable SQLite foreign key cascade support
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    user_id = None
    async with session_factory() as session:
        user = User(
            email="cascade@example.com",
            password_hash="hashed_pw",
        )
        session.add(user)
        await session.flush()
        user_id = user.id

        token1 = RefreshToken(
            user_id=user.id,
            token_hash="1" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        token2 = RefreshToken(
            user_id=user.id,
            token_hash="2" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.add_all([token1, token2])
        await session.commit()

    # Verify tokens exist
    async with session_factory() as session:
        persisted_user = await session.get(User, user_id)
        assert persisted_user is not None
        # Delete user
        await session.delete(persisted_user)
        await session.commit()

    # Verify tokens are deleted via cascade
    async with session_factory() as session:
        remaining_user = await session.get(User, user_id)
        assert remaining_user is None
        result = await session.execute(select(RefreshToken).where(RefreshToken.user_id == user_id))
        tokens = result.scalars().all()
        assert len(tokens) == 0

    await engine.dispose()
