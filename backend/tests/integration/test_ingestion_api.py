"""Integration tests for Ingestion API endpoints (/api/v1/documents/{doc_id}/ingest) (Chunk 4.4).

Covers test cases:
- I014: Status endpoint enforces authorization and anti-enumeration 404
- Unauthenticated requests return 401
- Trigger re-ingestion returns 202 Accepted
- Single job detail lookup
- Safe job cancellation
"""

from pathlib import Path
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, JobStatus
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from app.services.auth.tokens import create_access_token
from app.services.ingestion_service import ingestion_service
from app.services.storage.local import LocalStorageService


@pytest.fixture
async def api_env(tmp_path: Path):
    """Fixture providing an AsyncClient with test DB and isolated storage."""
    db_file = tmp_path / "test_ingestion_api.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

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

    custom_storage = LocalStorageService(base_dir=str(storage_dir))
    ingestion_service.storage = custom_storage

    # Create users
    async with session_factory() as s:
        user_a = User(
            email="usera@example.com",
            password_hash=hash_password("Pass1234!"),
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        user_b = User(
            email="userb@example.com",
            password_hash=hash_password("Pass1234!"),
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        admin = User(
            email="admin_ingest@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        s.add_all([user_a, user_b, admin])
        await s.commit()
        await s.refresh(user_a)
        await s.refresh(user_b)
        await s.refresh(admin)

        token_a = create_access_token(user_a.id, user_a.email, user_a.role.value)
        token_b = create_access_token(user_b.id, user_b.email, user_b.role.value)
        token_admin = create_access_token(admin.id, admin.email, admin.role.value)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory, custom_storage, user_a, user_b, admin, token_a, token_b, token_admin

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_i014_unauthenticated_request_returns_401(api_env) -> None:
    """Unauthenticated requests to ingestion endpoints return 401."""
    client, _, _, _, _, _, _, _, _ = api_env
    doc_id = uuid.uuid4()

    resp = await client.get(f"/api/v1/documents/{doc_id}/ingest/status")
    assert resp.status_code == 401

    resp_post = await client.post(f"/api/v1/documents/{doc_id}/ingest")
    assert resp_post.status_code == 401


@pytest.mark.asyncio
async def test_i014_anti_enumeration_returns_404_for_unauthorized_user(api_env) -> None:
    """I014: User B requesting ingestion status or trigger for User A's doc returns 404."""
    client, session_factory, storage, user_a, user_b, _, token_a, token_b, _ = api_env

    # Create document for User A
    async with session_factory() as s:
        doc = Document(
            filename="user_a_doc.txt",
            storage_key="documents/user_a_doc.txt",
            content_type="text/plain",
            file_size=50,
            checksum="chk_user_a",
            uploader_id=user_a.id,
        )
        s.add(doc)
        await s.commit()
        await s.refresh(doc)
        doc_id = doc.id

    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B status request
    resp_get = await client.get(f"/api/v1/documents/{doc_id}/ingest/status", headers=headers_b)
    assert resp_get.status_code == 404
    assert resp_get.json()["error"]["code"] == "NOT_FOUND"

    # User B trigger request
    resp_post = await client.post(f"/api/v1/documents/{doc_id}/ingest", headers=headers_b)
    assert resp_post.status_code == 404


@pytest.mark.asyncio
async def test_owner_and_admin_can_access_ingestion_status(api_env) -> None:
    """Owner and Admin can view ingestion status and history."""
    client, session_factory, storage, user_a, _, admin, token_a, _, token_admin = api_env

    storage_key = "documents/owner_doc.txt"
    await storage.save_bytes(storage_key, b"Testing owner and admin access to ingestion.")

    async with session_factory() as s:
        doc = Document(
            filename="owner_doc.txt",
            storage_key=storage_key,
            content_type="text/plain",
            file_size=45,
            checksum="chk_owner",
            uploader_id=user_a.id,
        )
        s.add(doc)
        await s.flush()

        job = IngestionJob(
            document_id=doc.id,
            status=JobStatus.SUCCEEDED,
            page_count=1,
            char_count=45,
            parser_name="text-parser",
            parser_version="1.0.0",
        )
        s.add(job)
        await s.commit()
        doc_id = doc.id
        job_id = job.id

    # 1. Owner views status
    resp_owner = await client.get(
        f"/api/v1/documents/{doc_id}/ingest/status",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_owner.status_code == 200
    data_owner = resp_owner.json()
    assert data_owner["documentId"] == str(doc_id)
    assert data_owner["currentJob"]["status"] == "succeeded"
    assert data_owner["currentJob"]["parserName"] == "text-parser"
    assert len(data_owner["history"]) == 1

    # 2. Admin views status
    resp_admin = await client.get(
        f"/api/v1/documents/{doc_id}/ingest/status",
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp_admin.status_code == 200

    # 3. View single job detail
    resp_detail = await client.get(
        f"/api/v1/documents/{doc_id}/ingest/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_detail.status_code == 200
    assert resp_detail.json()["id"] == str(job_id)


@pytest.mark.asyncio
async def test_trigger_reingestion_and_cancellation(api_env) -> None:
    """Triggering re-ingestion returns 202 and can be cancelled."""
    client, session_factory, storage, user_a, _, _, token_a, _, _ = api_env

    storage_key = "documents/reingest.txt"
    await storage.save_bytes(storage_key, b"Content for re-ingest test")

    async with session_factory() as s:
        doc = Document(
            filename="reingest.txt",
            storage_key=storage_key,
            content_type="text/plain",
            file_size=25,
            checksum="chk_reingest",
            uploader_id=user_a.id,
            status=DocumentStatus.FAILED,
        )
        s.add(doc)
        await s.commit()
        doc_id = doc.id

    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Trigger re-ingestion with force
    resp_trigger = await client.post(
        f"/api/v1/documents/{doc_id}/ingest",
        json={"forceReprocess": True},
        headers=headers_a,
    )
    assert resp_trigger.status_code == 202
    job_data = resp_trigger.json()
    assert job_data["documentId"] == str(doc_id)
    job_id = job_data["id"]

    # Cancel the job
    resp_cancel = await client.post(
        f"/api/v1/documents/{doc_id}/ingest/jobs/{job_id}/cancel",
        headers=headers_a,
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["status"] == "cancelled"
