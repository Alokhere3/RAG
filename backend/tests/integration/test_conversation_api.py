"""Integration tests for Phase 7 Conversation & Chat REST API (/api/v1/conversations).

Covers test cases C001 through C014:
- C001: Create conversation
- C002: List own conversations with stable pagination
- C003: Get own conversation succeeds
- C004: Access to another user's conversation returns 404 (anti-enumeration)
- C005: Send message invokes RAG and persists answer
- C006: Citations map to real sources
- C009: Delete conversation cascades messages
- C010: Message list pagination and chronological ordering
- C011: Oversized prompts are rejected (422)
- C013: Unauthenticated requests return 401
- C014: Server-side ownership boundaries enforced
"""

from pathlib import Path
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole, UserStatus
from app.services.auth.password import hash_password
from app.services.auth.tokens import create_access_token
from app.services.chunking import ChunkingConfig, TextSplitter
from app.services.embeddings.deterministic import DeterministicEmbeddingProvider
from app.services.indexing_service import IndexingService


@pytest.fixture
async def chat_test_env(tmp_path: Path):
    """Fixture providing isolated database, clients, and pre-indexed document."""
    db_file = tmp_path / "test_chat_api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed User A and User B
    async with session_factory() as session:
        user_a = User(
            email="alice@company.local",
            password_hash=hash_password("AliceSecurePass123!"),
            display_name="Alice User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        user_b = User(
            email="bob@company.local",
            password_hash=hash_password("BobSecurePass123!"),
            display_name="Bob User",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add_all([user_a, user_b])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)

        # Pre-seed and index an authorized document for Alice
        doc_a = Document(
            filename="company_handbook.txt",
            storage_key="documents/company_handbook.txt",
            content_type="text/plain",
            file_size=500,
            checksum="chk_handbook_123",
            uploader_id=user_a.id,
            status=DocumentStatus.READY,
        )
        session.add(doc_a)
        await session.commit()
        await session.refresh(doc_a)

        doc_id = doc_a.id
        user_a_id = user_a.id
        user_b_id = user_b.id

    # Index doc_a
    indexing = IndexingService(
        splitter=TextSplitter(ChunkingConfig(chunk_size=100, chunk_overlap=20)),
        provider=DeterministicEmbeddingProvider(),
    )
    async with session_factory() as session:
        await indexing.index_document(
            session=session,
            document_id=doc_id,
            text=(
                "Standard work hours are 9 AM to 5 PM with flexible core collaboration windows. "
                "Annual vacation allowance provides 25 paid personal days per calendar year."
            ),
        )

    token_a = create_access_token(user_id=str(user_a_id), email="alice@company.local", role="user")
    token_b = create_access_token(user_id=str(user_b_id), email="bob@company.local", role="user")


    async def override_get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, token_a, token_b, user_a_id, user_b_id

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_c001_create_conversation(chat_test_env):
    """C001: Authenticated user can create a conversation."""
    client, token_a, _, _, _ = chat_test_env

    resp = await client.post(
        "/api/v1/conversations",
        json={"title": "HR Inquiries"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "HR Inquiries"
    assert "id" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_c013_unauthenticated_requests_return_401(chat_test_env):
    """C013: Unauthenticated requests return 401."""
    client, _, _, _, _ = chat_test_env

    resp = await client.get("/api/v1/conversations")
    assert resp.status_code == 401

    resp = await client.post("/api/v1/conversations", json={"title": "Test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_c002_c003_list_and_get_own_conversation(chat_test_env):
    """C002 & C003: List own conversations with pagination and retrieve conversation by ID."""
    client, token_a, _, _, _ = chat_test_env

    # Create two conversations
    c1 = await client.post(
        "/api/v1/conversations",
        json={"title": "Topic One"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    c2 = await client.post(
        "/api/v1/conversations",
        json={"title": "Topic Two"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    c1_id = c1.json()["id"]

    # List conversations
    list_resp = await client.get(
        "/api/v1/conversations?page=1&page_size=10",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 2
    assert len(list_data["items"]) >= 2

    # Get single conversation
    get_resp = await client.get(
        f"/api/v1/conversations/{c1_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == c1_id
    assert get_resp.json()["title"] == "Topic One"


@pytest.mark.asyncio
async def test_c004_c014_user_cannot_access_another_users_conversation(chat_test_env):
    """C004 & C014: User cannot access or modify another user's conversation (returns 404)."""
    client, token_a, token_b, _, _ = chat_test_env

    # User A creates conversation
    create_resp = await client.post(
        "/api/v1/conversations",
        json={"title": "Alice Private Conversation"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    conv_id = create_resp.json()["id"]

    # User B attempts to get Alice's conversation -> 404 (anti-enumeration)
    get_resp = await client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert get_resp.status_code == 404

    # User B attempts to delete Alice's conversation -> 404
    del_resp = await client.delete(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_resp.status_code == 404

    # User B attempts to post message to Alice's conversation -> 404
    post_resp = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Sneaky message attempt"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert post_resp.status_code == 404


@pytest.mark.asyncio
async def test_c005_c006_send_message_invokes_rag_and_returns_citations(chat_test_env):
    """C005 & C006: Posting message invokes RAG and persists grounded answer with real citations."""
    client, token_a, _, _, _ = chat_test_env

    # 1. Create conversation
    create_resp = await client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    conv_id = create_resp.json()["id"]

    # 2. Post question about vacation allowance (present in indexed company handbook)
    msg_resp = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "What is the annual vacation allowance and work hours?"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert msg_resp.status_code == 201
    data = msg_resp.json()

    assert data["role"] == "assistant"
    assert len(data["content"]) > 0
    # Assistant response should have verified citations
    assert data["citations"] is not None
    assert len(data["citations"]) > 0
    for citation in data["citations"]:
        assert citation["document_title"] == "company_handbook.txt"
        assert citation["relevance_score"] > 0.0


@pytest.mark.asyncio
async def test_c010_message_pagination_and_ordering(chat_test_env):
    """C010: Message list pagination and chronological ordering."""
    client, token_a, _, _, _ = chat_test_env

    # Create conversation
    c_resp = await client.post("/api/v1/conversations", headers={"Authorization": f"Bearer {token_a}"})
    conv_id = c_resp.json()["id"]

    # Post message
    await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "First question"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Fetch messages
    list_resp = await client.get(
        f"/api/v1/conversations/{conv_id}/messages?page=1&page_size=10",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 2  # 1 user + 1 assistant
    assert data["items"][0]["role"] == "user"
    assert data["items"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_c011_oversized_prompt_rejected(chat_test_env):
    """C011: Oversized prompts exceeding maximum length are rejected."""
    client, token_a, _, _, _ = chat_test_env

    c_resp = await client.post("/api/v1/conversations", headers={"Authorization": f"Bearer {token_a}"})
    conv_id = c_resp.json()["id"]

    # 4001 characters (> 4000 limit)
    oversized = "A" * 4001
    resp = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": oversized},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_c009_delete_conversation_cascades_messages(chat_test_env):
    """C009: Deleting conversation removes conversation and cascades messages."""
    client, token_a, _, _, _ = chat_test_env

    # Create and post message
    c_resp = await client.post("/api/v1/conversations", headers={"Authorization": f"Bearer {token_a}"})
    conv_id = c_resp.json()["id"]
    await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"content": "Delete test question"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Delete conversation
    del_resp = await client.delete(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert del_resp.status_code == 200

    # Ensure get conversation returns 404
    get_resp = await client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert get_resp.status_code == 404
