"""Integration tests for Phase 8 Administration & Operations (O001-O013)."""

import logging
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, JobStatus
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from app.services.auth.tokens import create_access_token


@pytest.fixture
async def admin_test_env(tmp_path):
    """Isolated SQLite test environment for administration workflows."""
    db_file = tmp_path / "test_admin.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed Admin User, Normal User, and a target test user
    async with session_factory() as session:
        admin_user = User(
            email="superadmin@company.local",
            password_hash=hash_password("SuperSecretAdmin123!"),
            display_name="Super Admin",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        normal_user = User(
            email="regularuser@company.local",
            password_hash=hash_password("RegularUserPassword123!"),
            display_name="Regular User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        target_user = User(
            email="targetuser@company.local",
            password_hash=hash_password("TargetUserPassword123!"),
            display_name="Target User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add_all([admin_user, normal_user, target_user])
        await session.commit()
        await session.refresh(admin_user)
        await session.refresh(normal_user)
        await session.refresh(target_user)

        admin_id = admin_user.id
        normal_id = normal_user.id
        target_id = target_user.id

        # Seed Document & Ingestion Jobs for testing
        doc = Document(
            filename="financial_summary.pdf",
            storage_key="documents/financial_summary.pdf",
            content_type="application/pdf",
            file_size=1024,
            checksum="chk_summary_123",
            uploader_id=normal_id,
            status=DocumentStatus.FAILED,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id

        # Failed job
        failed_job = IngestionJob(
            document_id=doc_id,
            status=JobStatus.FAILED,
            attempt_count=3,
            max_attempts=3,
            error_code="PARSER_TIMEOUT",
            error_message="Timed out during text extraction.",
        )
        # Succeeded job
        succeeded_job = IngestionJob(
            document_id=doc_id,
            status=JobStatus.SUCCEEDED,
            attempt_count=1,
            max_attempts=3,
        )
        session.add_all([failed_job, succeeded_job])
        await session.commit()
        await session.refresh(failed_job)
        await session.refresh(succeeded_job)

        failed_job_id = failed_job.id
        succeeded_job_id = succeeded_job.id

    admin_token = create_access_token(user_id=str(admin_id), email="superadmin@company.local", role="admin")
    normal_token = create_access_token(user_id=str(normal_id), email="regularuser@company.local", role="user")

    async def override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, admin_token, normal_token, admin_id, normal_id, target_id, failed_job_id, succeeded_job_id

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_o001_admin_can_list_and_create_users(admin_test_env):
    """O001: Admin can list system users and create a new user account within policy."""
    client, admin_token, _, _, _, _, _, _ = admin_test_env

    # 1. List users
    resp = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 3
    assert len(data["items"]) >= 3

    # 2. Create user with valid policy
    create_resp = await client.post(
        "/api/v1/admin/users",
        json={
            "email": "newemployee@company.local",
            "password": "SecurePassword123!",
            "display_name": "New Employee",
            "role": "user",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    created_user = create_resp.json()
    assert created_user["email"] == "newemployee@company.local"
    assert created_user["role"] == "user"
    assert created_user["status"] == "active"
    assert "password" not in created_user
    assert "password_hash" not in created_user


@pytest.mark.asyncio
async def test_o002_normal_user_cannot_access_admin_endpoints(admin_test_env):
    """O002: Normal non-admin user cannot access admin routes (403 Forbidden)."""
    client, _, normal_token, _, _, target_id, failed_job_id, _ = admin_test_env

    headers = {"Authorization": f"Bearer {normal_token}"}

    # User list forbidden
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403

    # User creation forbidden
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": "hacker@evil.local", "password": "Password123!"},
        headers=headers,
    )
    assert resp.status_code == 403

    # Role update forbidden
    resp = await client.patch(
        f"/api/v1/admin/users/{target_id}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert resp.status_code == 403

    # Status update forbidden
    resp = await client.patch(
        f"/api/v1/admin/users/{target_id}/status",
        json={"status": "suspended"},
        headers=headers,
    )
    assert resp.status_code == 403

    # Document list forbidden
    resp = await client.get("/api/v1/admin/documents", headers=headers)
    assert resp.status_code == 403

    # Jobs list forbidden
    resp = await client.get("/api/v1/admin/ingestion/jobs", headers=headers)
    assert resp.status_code == 403

    # Retry job forbidden
    resp = await client.post(f"/api/v1/admin/ingestion/jobs/{failed_job_id}/retry", headers=headers)
    assert resp.status_code == 403

    # Diagnostics forbidden
    resp = await client.get("/api/v1/admin/diagnostics/config", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_o003_role_change_authorized_and_audited(admin_test_env, caplog):
    """O003 & O012: Admin updates user role from user to admin, change is audited."""
    client, admin_token, _, _, _, target_id, _, _ = admin_test_env

    with caplog.at_level(logging.INFO):
        resp = await client.patch(
            f"/api/v1/admin/users/{target_id}/role",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"

        # Verify structured audit log entry (O012)
        audit_records = [r for r in caplog.records if "ADMIN_ACTION_AUDIT" in r.message]
        assert len(audit_records) > 0
        assert "action=UPDATE_ROLE" in audit_records[-1].message
        assert str(target_id) in audit_records[-1].message
        assert "password" not in audit_records[-1].message.lower()


@pytest.mark.asyncio
async def test_o004_normal_user_cannot_change_roles(admin_test_env):
    """O004: Normal user cannot elevate privileges or modify roles (403)."""
    client, _, normal_token, _, normal_id, _, _, _ = admin_test_env

    resp = await client.patch(
        f"/api/v1/admin/users/{normal_id}/role",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_o005_last_admin_protection(admin_test_env):
    """O005: Attempting to demote or deactivate the last active admin is rejected (400)."""
    client, admin_token, _, admin_id, _, _, _, _ = admin_test_env

    headers = {"Authorization": f"Bearer {admin_token}"}

    # Attempt to demote the only active admin
    demote_resp = await client.patch(
        f"/api/v1/admin/users/{admin_id}/role",
        json={"role": "user"},
        headers=headers,
    )
    assert demote_resp.status_code == 400
    assert "last remaining active administrator" in demote_resp.json()["error"]["message"]

    # Attempt to deactivate / suspend the only active admin
    deactivate_resp = await client.patch(
        f"/api/v1/admin/users/{admin_id}/status",
        json={"status": "suspended"},
        headers=headers,
    )
    assert deactivate_resp.status_code == 400
    assert "last remaining active administrator" in deactivate_resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_o006_admin_views_system_documents_and_jobs(admin_test_env):
    """O006: Admin can inspect documents and ingestion jobs system-wide."""
    client, admin_token, _, _, _, _, _, _ = admin_test_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Documents
    doc_resp = await client.get("/api/v1/admin/documents", headers=headers)
    assert doc_resp.status_code == 200
    docs = doc_resp.json()
    assert docs["total"] >= 1
    assert "storage_key" not in docs["items"][0]  # internal storage path masked

    # Jobs
    job_resp = await client.get("/api/v1/admin/ingestion/jobs", headers=headers)
    assert job_resp.status_code == 200
    jobs = job_resp.json()
    assert jobs["total"] >= 2


@pytest.mark.asyncio
async def test_o007_retry_failed_job_safe_and_idempotent(admin_test_env, caplog):
    """O007: Admin can safely retry a failed ingestion job and it is audited."""
    client, admin_token, _, _, _, _, failed_job_id, _ = admin_test_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    with caplog.at_level(logging.INFO):
        resp = await client.post(
            f"/api/v1/admin/ingestion/jobs/{failed_job_id}/retry",
            headers=headers,
        )
        assert resp.status_code == 200

        # Audit log present
        audit_records = [r for r in caplog.records if "ADMIN_ACTION_AUDIT" in r.message]
        assert len(audit_records) > 0
        assert "action=RETRY_JOB" in audit_records[-1].message


@pytest.mark.asyncio
async def test_o008_retry_completed_job_deterministic_behavior(admin_test_env):
    """O008: Retrying an already succeeded job returns deterministic 400 Bad Request."""
    client, admin_token, _, _, _, _, _, succeeded_job_id = admin_test_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = await client.post(
        f"/api/v1/admin/ingestion/jobs/{succeeded_job_id}/retry",
        headers=headers,
    )
    assert resp.status_code == 400
    assert "already succeeded" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_o009_diagnostics_expose_no_secrets(admin_test_env):
    """O009: Configuration diagnostics expose runtime metadata but zero secrets."""
    client, admin_token, _, _, _, _, _, _ = admin_test_env
    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = await client.get("/api/v1/admin/diagnostics/config", headers=headers)
    assert resp.status_code == 200
    diag = resp.json()

    # Required diagnostic sections
    assert "application" in diag
    assert "security" in diag
    assert "embedding" in diag
    assert "llm" in diag
    assert "features" in diag

    raw_str = str(diag).lower()
    # Zero secrets exposed
    assert "jwt_secret" not in raw_str
    assert "secret_key" not in raw_str
    assert "database_url" not in raw_str
    assert "redis_url" not in raw_str
    assert "api_key" not in raw_str
    assert "password_hash" not in raw_str
    assert "db_password" not in raw_str
    assert "postgres" not in raw_str
