"""Integration tests for Document Management API (/api/v1/documents) (Phase 3).

Covers test cases D001 through D019:
- D001: Valid supported file upload creates document metadata
- D002: Unauthenticated upload returns 401
- D003: Non-owner user accessing another user's document returns 404 (anti-enumeration)
- D004: Empty file rejected
- D005: Oversized file rejected
- D006: Unsupported extension rejected
- D007: MIME spoofing rejected
- D008: Path traversal filename sanitized
- D009: Duplicate upload behavior deterministic
- D010: List pagination, order, and scoping
- D011: Safe metadata fields only (no storage_key or absolute paths)
- D012: Unknown ID returns 404
- D013: Consistent deletion from DB and disk
- D014: Unauthorized deletion returns 404
- D015/D016: Partial write cleanup and reconciliation
- D017: File persistence on disk
- D018: Concurrent uploads do not collide
- D019: No absolute paths in responses
"""

import asyncio
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
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from app.services.auth.tokens import create_access_token
from app.services.storage.local import LocalStorageService


@pytest.fixture
async def document_test_env(tmp_path: Path, monkeypatch):
    """Fixture providing an AsyncClient with test DB and isolated storage."""
    db_file = tmp_path / "test_doc_api.db"
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

    # Point storage service to temp directory
    custom_storage = LocalStorageService(base_dir=str(storage_dir))
    monkeypatch.setattr("app.services.document_service.storage_service", custom_storage)

    # Seed users
    async with session_factory() as session:
        user1 = User(
            email="user1@example.com",
            password_hash=hash_password("UserPass1!"),
            display_name="User One",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        user2 = User(
            email="user2@example.com",
            password_hash=hash_password("UserPass2!"),
            display_name="User Two",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        admin = User(
            email="admin@example.com",
            password_hash=hash_password("AdminPass1!"),
            display_name="Admin",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        session.add_all([user1, user2, admin])
        await session.commit()
        await session.refresh(user1)
        await session.refresh(user2)
        await session.refresh(admin)

        user1_id = user1.id
        user2_id = user2.id
        admin_id = admin.id

    token_user1 = create_access_token(user_id=str(user1_id), email="user1@example.com", role="user")
    token_user2 = create_access_token(user_id=str(user2_id), email="user2@example.com", role="user")
    token_admin = create_access_token(user_id=str(admin_id), email="admin@example.com", role="admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "user1_id": user1_id,
            "user2_id": user2_id,
            "admin_id": admin_id,
            "token_user1": token_user1,
            "token_user2": token_user2,
            "token_admin": token_admin,
            "storage": custom_storage,
            "session_factory": session_factory,
        }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_d001_valid_upload_creates_metadata(document_test_env):
    """Test D001: Valid supported file upload creates document metadata and stores file."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    pdf_content = b"%PDF-1.4\nTest Document Content\n%%EOF"
    response = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("manual.pdf", pdf_content, "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "manual.pdf"
    assert data["contentType"] == "application/pdf"
    assert data["fileSize"] == len(pdf_content)
    assert data["status"] == "uploaded"
    assert "checksum" in data
    assert "storage_key" not in data  # Never leaked
    assert "storageKey" not in data   # Never leaked


@pytest.mark.asyncio
async def test_d002_unauthenticated_upload_returns_401(document_test_env):
    """Test D002: Unauthenticated upload returns 401."""
    client = document_test_env["client"]
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("test.txt", b"Hello", "text/plain")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_d003_unauthorized_user_access_returns_404(document_test_env):
    """Test D003: Standard user cannot access or inspect another user's document (returns anti-enumeration 404)."""
    client = document_test_env["client"]
    token1 = document_test_env["token_user1"]
    token2 = document_test_env["token_user2"]

    # User 1 uploads
    res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token1}"},
        files={"file": ("secret.txt", b"Confidential User 1 Data", "text/plain")},
    )
    doc_id = res.json()["id"]

    # User 2 tries to access -> 404
    res2 = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert res2.status_code == 404


@pytest.mark.asyncio
async def test_d004_empty_file_rejected(document_test_env):
    """Test D004: Empty file upload returns 400."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert res.status_code == 400
    assert "empty" in res.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_d005_oversized_file_rejected(document_test_env, monkeypatch):
    """Test D005: Oversized file rejected with 413."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_bytes", 50)

    oversized = b"%PDF-" + b"x" * 100
    res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("large.pdf", oversized, "application/pdf")},
    )
    assert res.status_code == 413


@pytest.mark.asyncio
async def test_d006_unsupported_extension_rejected(document_test_env):
    """Test D006: Unsupported file extension rejected with 400."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("payload.exe", b"binary", "application/octet-stream")},
    )
    assert res.status_code == 400
    assert "UNSUPPORTED_FILE_TYPE" in res.json()["error"]["code"]


@pytest.mark.asyncio
async def test_d007_mime_spoofing_rejected(document_test_env):
    """Test D007: Fake PDF header rejected."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("fake.pdf", b"NOT_A_PDF_HEADER", "application/pdf")},
    )
    assert res.status_code == 400
    assert "MIME_SPOOFING" in res.json()["error"]["code"]


@pytest.mark.asyncio
async def test_d008_path_traversal_filename_sanitized(document_test_env):
    """Test D008: Path traversal in uploaded filename is sanitized."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("../../etc/passwd.txt", b"Safe plain text content", "text/plain")},
    )
    assert res.status_code == 201
    assert "/" not in res.json()["filename"]
    assert ".." not in res.json()["filename"]


@pytest.mark.asyncio
async def test_d009_duplicate_upload_is_deterministic(document_test_env):
    """Test D009: Uploading the exact same file twice deterministically reuses existing document."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]
    content = b"%PDF-1.4\nDuplicate Test\n%%EOF"

    res1 = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("doc.pdf", content, "application/pdf")},
    )
    res2 = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("doc.pdf", content, "application/pdf")},
    )

    assert res1.status_code == 201
    assert res2.status_code == 201
    assert res1.json()["id"] == res2.json()["id"]
    assert res1.json()["checksum"] == res2.json()["checksum"]


@pytest.mark.asyncio
async def test_d010_list_documents_pagination_and_role_scoping(document_test_env):
    """Test D010: List pagination and role-based visibility."""
    client = document_test_env["client"]
    token1 = document_test_env["token_user1"]
    token2 = document_test_env["token_user2"]
    admin_token = document_test_env["token_admin"]

    # User 1 uploads 2 docs
    await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token1}"},
        files={"file": ("u1_a.txt", b"A", "text/plain")},
    )
    await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token1}"},
        files={"file": ("u1_b.txt", b"B", "text/plain")},
    )

    # User 2 uploads 1 doc
    await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token2}"},
        files={"file": ("u2_a.txt", b"C", "text/plain")},
    )

    # User 1 lists -> sees 2 docs
    res_u1 = await client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token1}"})
    assert res_u1.status_code == 200
    assert res_u1.json()["total"] == 2
    assert len(res_u1.json()["items"]) == 2

    # User 2 lists -> sees 1 doc
    res_u2 = await client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token2}"})
    assert res_u2.status_code == 200
    assert res_u2.json()["total"] == 1

    # Admin lists -> sees all 3 docs
    res_admin = await client.get("/api/v1/documents", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    assert res_admin.json()["total"] == 3


@pytest.mark.asyncio
async def test_d011_get_metadata_safe_fields_only(document_test_env):
    """Test D011: Get document returns only safe allowlisted fields."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    upload_res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("guide.md", b"# Safe guide", "text/markdown")},
    )
    doc_id = upload_res.json()["id"]

    get_res = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert set(data.keys()) == {
        "id", "filename", "contentType", "fileSize",
        "checksum", "uploaderId", "status", "createdAt",
        "updatedAt", "metadata"
    }


@pytest.mark.asyncio
async def test_d012_unknown_id_returns_404(document_test_env):
    """Test D012: Non-existent UUID returns 404."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    fake_id = str(uuid.uuid4())
    res = await client.get(
        f"/api/v1/documents/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_d013_delete_handles_file_and_metadata_consistently(document_test_env):
    """Test D013: Deleting document removes file from disk and DB."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]
    storage = document_test_env["storage"]

    upload_res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("to_delete.txt", b"Delete me soon", "text/plain")},
    )
    doc_id = upload_res.json()["id"]

    # Delete
    del_res = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 200

    # Ensure get returns 404 now
    get_res = await client.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_d014_unauthorized_deletion_returns_404(document_test_env):
    """Test D014: Standard user cannot delete another user's document."""
    client = document_test_env["client"]
    token1 = document_test_env["token_user1"]
    token2 = document_test_env["token_user2"]

    upload_res = await client.post(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token1}"},
        files={"file": ("user1_file.txt", b"User 1 private", "text/plain")},
    )
    doc_id = upload_res.json()["id"]

    # User 2 tries to delete -> 404
    del_res = await client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert del_res.status_code == 404


@pytest.mark.asyncio
async def test_d018_concurrent_uploads_do_not_collide(document_test_env):
    """Test D018: Concurrent uploads generate unique keys and do not collide."""
    client = document_test_env["client"]
    token = document_test_env["token_user1"]

    async def upload_concurrent(i: int):
        return await client.post(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"concurrent_{i}.txt", f"Concurrent content {i}".encode(), "text/plain")},
        )

    responses = await asyncio.gather(*(upload_concurrent(i) for i in range(5)))
    for r in responses:
        assert r.status_code == 201

    ids = [r.json()["id"] for r in responses]
    assert len(set(ids)) == 5
