"""Tests verifying PII (email, passwords, tokens) is never emitted to authentication logs (F-10)."""

from datetime import datetime, timezone
import logging
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password


@pytest.fixture
async def auth_test_context(tmp_path: Path):
    """Fixture providing an AsyncClient and db session factory with clean database."""
    db_file = tmp_path / "test_auth_log_privacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_login_logs_do_not_contain_email_or_password(auth_test_context, caplog):
    """Ensure login failure and success never log user email or password."""
    client, session_factory = auth_test_context
    secret_password = "SecretUserPass123!"
    user_email = "sensitive_pii_user@securecorp.com"

    # Create active user
    async with session_factory() as session:
        user = User(
            email=user_email,
            password_hash=hash_password(secret_password),
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    # 1. Test Login Failure Path
    with caplog.at_level(logging.INFO):
        caplog.clear()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "WrongPassword123!"},
        )
        assert resp.status_code == 401

        # Assert user_email is NOT in any log record
        for record in caplog.records:
            assert user_email not in record.message
            assert "WrongPassword123!" not in record.message
            assert secret_password not in record.message

    # 2. Test Login Success Path
    with caplog.at_level(logging.INFO):
        caplog.clear()
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": secret_password},
        )
        assert resp.status_code == 200

        # Assert user_email and password are NOT in any log record
        for record in caplog.records:
            assert user_email not in record.message
            assert secret_password not in record.message
            if "LOGIN_SUCCESS" in record.message:
                # User ID is logged, but NOT email
                assert str(user_id) in record.message
                assert "@" not in record.message
