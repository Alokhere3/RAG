"""Integration tests for Authorization and Protected API dependencies (Chunk 2.6).

Validates the full authorization matrix:
- HTTP 401 for unauthenticated / invalid token conditions
- HTTP 403 for authenticated but unauthorized (insufficient role / inactive status)
- Role hierarchy enforcement (ADMIN supervisory over USER)
"""

from datetime import timedelta
from pathlib import Path
import uuid
import jwt
import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_current_user, require_admin, require_role, require_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from app.services.auth.tokens import create_access_token
from app.core.config import get_settings


@pytest.fixture
async def authz_test_env(tmp_path: Path):
    """Fixture providing an AsyncClient with test routes and seed accounts."""
    db_file = tmp_path / "test_authz.db"
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

    # Create temporary test endpoints to exercise authorization dependencies
    test_router = APIRouter(prefix="/api/v1/test-authz", tags=["TestAuthz"])

    @test_router.get("/user-only")
    async def user_only_route(current_user: User = Depends(require_user)):
        return {"status": "ok", "user": current_user.email, "role": current_user.role.value}

    @test_router.get("/admin-only")
    async def admin_only_route(current_admin: User = Depends(require_admin)):
        return {"status": "ok", "admin": current_admin.email, "role": current_admin.role.value}

    app.include_router(test_router)

    users = {}
    async with session_factory() as session:
        standard_user = User(
            email="standard@platform.local",
            password_hash=hash_password("StandardPass123!"),
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        admin_user = User(
            email="admin@platform.local",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        suspended_user = User(
            email="suspended@platform.local",
            password_hash=hash_password("SuspendedPass123!"),
            role=UserRole.USER,
            status=UserStatus.SUSPENDED,
        )
        inactive_user = User(
            email="inactive@platform.local",
            password_hash=hash_password("InactivePass123!"),
            role=UserRole.USER,
            status=UserStatus.INACTIVE,
        )
        session.add_all([standard_user, admin_user, suspended_user, inactive_user])
        await session.commit()
        await session.refresh(standard_user)
        await session.refresh(admin_user)
        await session.refresh(suspended_user)
        await session.refresh(inactive_user)

        users["user"] = standard_user
        users["admin"] = admin_user
        users["suspended"] = suspended_user
        users["inactive"] = inactive_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, users

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_no_token_returns_401(authz_test_env):
    """Verify requests with no Authorization header are rejected with 401."""
    client, _ = authz_test_env
    response = await client.get("/api/v1/test-authz/user-only")

    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.asyncio
async def test_malformed_token_returns_401(authz_test_env):
    """Verify completely malformed Authorization headers return 401."""
    client, _ = authz_test_env
    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": "Bearer this-is-not-a-jwt"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_expired_token_returns_401(authz_test_env):
    """Verify expired access tokens return 401 with TOKEN_EXPIRED code."""
    client, users = authz_test_env
    expired_token = create_access_token(
        user_id=users["user"].id,
        email=users["user"].email,
        role=users["user"].role.value,
        expires_delta=timedelta(seconds=-30),
    )

    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_invalid_signature_returns_401(authz_test_env):
    """Verify tokens signed with untrusted secret return 401."""
    client, users = authz_test_env
    tampered_token = jwt.encode(
        {
            "sub": str(users["user"].id),
            "email": users["user"].email,
            "role": "admin",  # Tampered role
            "type": "access",
            "iat": 1000,
            "exp": 9999999999,
            "jti": str(uuid.uuid4()),
        },
        "attacker-secret-key-that-does-not-match",
        algorithm="HS256",
    )

    response = await client.get(
        "/api/v1/test-authz/admin-only",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_wrong_token_type_returns_401(authz_test_env):
    """Verify token with wrong type claim (e.g. refresh) returns 401."""
    client, users = authz_test_env
    settings = get_settings()
    secret = settings.jwt_secret.get_secret_value() or "rag-dev-jwt-insecure-secret-key-32chars-min-padding"

    wrong_type_token = jwt.encode(
        {
            "sub": str(users["user"].id),
            "email": users["user"].email,
            "role": "user",
            "type": "refresh",  # Should be 'access'
            "iat": 1000,
            "exp": 9999999999,
            "jti": str(uuid.uuid4()),
        },
        secret,
        algorithm="HS256",
    )

    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": f"Bearer {wrong_type_token}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_suspended_user_denied_with_403(authz_test_env):
    """Verify valid token for a suspended user is denied with 403 USER_INACTIVE."""
    client, users = authz_test_env
    token = create_access_token(
        user_id=users["suspended"].id,
        email=users["suspended"].email,
        role=users["suspended"].role.value,
    )

    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_inactive_user_denied_with_403(authz_test_env):
    """Verify valid token for an inactive user is denied with 403 USER_INACTIVE."""
    client, users = authz_test_env
    token = create_access_token(
        user_id=users["inactive"].id,
        email=users["inactive"].email,
        role=users["inactive"].role.value,
    )

    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_INACTIVE"


@pytest.mark.asyncio
async def test_valid_user_accesses_user_route(authz_test_env):
    """Verify active user accesses user-protected route successfully with 200."""
    client, users = authz_test_env
    token = create_access_token(
        user_id=users["user"].id,
        email=users["user"].email,
        role=users["user"].role.value,
    )

    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["user"] == "standard@platform.local"


@pytest.mark.asyncio
async def test_standard_user_denied_admin_route_with_403(authz_test_env):
    """Verify standard user attempting admin route is denied with 403 FORBIDDEN."""
    client, users = authz_test_env
    token = create_access_token(
        user_id=users["user"].id,
        email=users["user"].email,
        role=users["user"].role.value,
    )

    response = await client.get(
        "/api/v1/test-authz/admin-only",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_allowed_on_admin_route(authz_test_env):
    """Verify admin user accesses admin-protected route with 200."""
    client, users = authz_test_env
    admin_token = create_access_token(
        user_id=users["admin"].id,
        email=users["admin"].email,
        role=users["admin"].role.value,
    )

    response = await client.get(
        "/api/v1/test-authz/admin-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_supervisory_access_on_user_route(authz_test_env):
    """Verify admin user also has supervisory access to user-protected route."""
    client, users = authz_test_env
    admin_token = create_access_token(
        user_id=users["admin"].id,
        email=users["admin"].email,
        role=users["admin"].role.value,
    )

    response = await client.get(
        "/api/v1/test-authz/user-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
