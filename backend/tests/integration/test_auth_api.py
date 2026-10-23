"""Integration tests for Authentication API endpoints (/api/v1/auth)."""

from datetime import datetime, timezone
from pathlib import Path
import uuid
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
async def auth_test_client(tmp_path: Path):
    """Fixture providing an AsyncClient with a clean SQLite test database and overridden get_db dependency."""
    db_file = tmp_path / "test_auth_api.db"
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

    # Seed initial test users
    async with session_factory() as session:
        active_user = User(
            email="testuser@example.com",
            password_hash=hash_password("ValidP@ssword123!"),
            display_name="Test User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        admin_user = User(
            email="admin@example.com",
            password_hash=hash_password("AdminP@ssword123!"),
            display_name="Admin User",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        suspended_user = User(
            email="suspended@example.com",
            password_hash=hash_password("SuspendedP@ss123!"),
            display_name="Suspended User",
            role=UserRole.USER,
            status=UserStatus.SUSPENDED,
        )
        session.add_all([active_user, admin_user, suspended_user])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_login_success(auth_test_client: AsyncClient):
    """Verify successful login returns user profile, access token, and HttpOnly refresh cookie."""
    response = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "ValidP@ssword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert "user" in data
    assert data["user"]["email"] == "testuser@example.com"
    assert data["user"]["displayName"] == "Test User"
    assert data["user"]["role"] == "user"
    assert data["user"]["status"] == "active"
    assert "password_hash" not in str(data)

    # Check cookies
    cookies = response.cookies
    assert "rag_refresh_token" in cookies
    cookie_header = response.headers.get("set-cookie", "")
    assert "httponly" in cookie_header.lower()
    assert "path=/api/v1/auth" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


@pytest.mark.asyncio
async def test_login_email_normalization(auth_test_client: AsyncClient):
    """Verify login succeeds when email has leading/trailing whitespace and uppercase characters."""
    response = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "   TESTUSER@EXAMPLE.COM   ", "password": "ValidP@ssword123!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "testuser@example.com"


@pytest.mark.asyncio
async def test_login_invalid_password_generic_error(auth_test_client: AsyncClient):
    """Verify wrong password returns 401 with generic error message preventing enumeration."""
    response = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "WrongPassword!"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"
    assert data["error"]["message"] == "Invalid email or password."
    assert "rag_refresh_token" not in response.cookies


@pytest.mark.asyncio
async def test_login_unknown_email_generic_error(auth_test_client: AsyncClient):
    """Verify non-existent email returns identical 401 generic error preventing enumeration."""
    response = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "SomePassword123!"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"
    assert data["error"]["message"] == "Invalid email or password."


@pytest.mark.asyncio
async def test_login_suspended_account(auth_test_client: AsyncClient):
    """Verify suspended accounts cannot log in."""
    response = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "suspended@example.com", "password": "SuspendedP@ss123!"},
    )

    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_get_me_endpoint(auth_test_client: AsyncClient):
    """Verify GET /api/v1/auth/me returns authenticated profile with Bearer token."""
    # 1. Without token -> 401
    unauth_resp = await auth_test_client.get("/api/v1/auth/me")
    assert unauth_resp.status_code == 401

    # 2. Login to get token
    login_resp = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminP@ssword123!"},
    )
    access_token = login_resp.json()["accessToken"]

    # 3. Request /me with token
    me_resp = await auth_test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == "admin@example.com"
    assert me_data["displayName"] == "Admin User"
    assert me_data["role"] == "admin"
    assert "password" not in str(me_data)


@pytest.mark.asyncio
async def test_refresh_token_rotation_flow(auth_test_client: AsyncClient):
    """Verify POST /api/v1/auth/refresh rotates the cookie and issues a new access token."""
    # 1. Login to establish cookie
    login_resp = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "ValidP@ssword123!"},
    )
    assert login_resp.status_code == 200
    token_1 = login_resp.json()["accessToken"]
    cookie_1 = login_resp.cookies["rag_refresh_token"]

    # 2. Call /refresh with cookie
    refresh_resp = await auth_test_client.post(
        "/api/v1/auth/refresh",
        cookies={"rag_refresh_token": cookie_1},
    )
    assert refresh_resp.status_code == 200
    refresh_data = refresh_resp.json()
    token_2 = refresh_data["accessToken"]
    cookie_2 = refresh_resp.cookies["rag_refresh_token"]

    assert token_2 != token_1
    assert cookie_2 != cookie_1  # Rotated!

    # 3. New access token works with /me
    me_resp = await auth_test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_2}"},
    )
    assert me_resp.status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_reuse_theft_mitigation(auth_test_client: AsyncClient):
    """Verify presenting an already rotated cookie triggers reuse invalidation."""
    # 1. Login
    login_resp = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "ValidP@ssword123!"},
    )
    cookie_1 = login_resp.cookies["rag_refresh_token"]

    # 2. Legitimate refresh consumes cookie 1
    await auth_test_client.post(
        "/api/v1/auth/refresh",
        cookies={"rag_refresh_token": cookie_1},
    )

    # 3. Attacker replays cookie 1
    replay_resp = await auth_test_client.post(
        "/api/v1/auth/refresh",
        cookies={"rag_refresh_token": cookie_1},
    )
    assert replay_resp.status_code == 401
    assert "INVALID_REFRESH_TOKEN" in replay_resp.json()["error"]["code"]


@pytest.mark.asyncio
async def test_logout_flow(auth_test_client: AsyncClient):
    """Verify logout clears cookie and invalidates session."""
    login_resp = await auth_test_client.post(
        "/api/v1/auth/login",
        json={"email": "testuser@example.com", "password": "ValidP@ssword123!"},
    )
    cookie = login_resp.cookies["rag_refresh_token"]

    # Logout
    logout_resp = await auth_test_client.post(
        "/api/v1/auth/logout",
        cookies={"rag_refresh_token": cookie},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Successfully logged out."

    # Try to refresh with logged-out cookie -> rejected
    refresh_resp = await auth_test_client.post(
        "/api/v1/auth/refresh",
        cookies={"rag_refresh_token": cookie},
    )
    assert refresh_resp.status_code == 401
