"""Integration tests for Phase 6 Retrieval & RAG Core (R001-R003, R006, R007, R010, R011, R017)."""

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole, UserStatus
from app.services.chunking import ChunkingConfig, TextSplitter
from app.services.embeddings.deterministic import DeterministicEmbeddingProvider
from app.services.indexing_service import IndexingService
from app.services.llm.deterministic import DeterministicLlmProvider
from app.services.rag.schemas import RagQueryRequest
from app.services.rag.service import INSUFFICIENT_EVIDENCE_ANSWER, RagService


@pytest.fixture
async def rag_test_db(tmp_path):
    """Isolated SQLite database fixture for RAG pipeline integration tests."""
    db_file = tmp_path / "test_rag.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed User A, User B, Admin
    async with session_factory() as session:
        user_a = User(
            email="usera@company.local",
            password_hash="argon2id$mockhash",
            display_name="User A",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        user_b = User(
            email="userb@company.local",
            password_hash="argon2id$mockhash",
            display_name="User B",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        admin = User(
            email="admin@company.local",
            password_hash="argon2id$mockhash",
            display_name="System Admin",
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )
        session.add_all([user_a, user_b, admin])
        await session.commit()
        await session.refresh(user_a)
        await session.refresh(user_b)
        await session.refresh(admin)

        # Document 1 (owned by User A, READY)
        doc_a = Document(
            filename="quantum_computing_guide.txt",
            storage_key="documents/quantum_computing_guide.txt",
            content_type="text/plain",
            file_size=600,
            checksum="checksum_doc_a",
            uploader_id=user_a.id,
            status=DocumentStatus.READY,
        )
        # Document 2 (owned by User B, READY)
        doc_b = Document(
            filename="financial_q3_report.txt",
            storage_key="documents/financial_q3_report.txt",
            content_type="text/plain",
            file_size=600,
            checksum="checksum_doc_b",
            uploader_id=user_b.id,
            status=DocumentStatus.READY,
        )
        # Document 3 (owned by User A, but NOT READY - pending ingestion)
        doc_pending = Document(
            filename="draft_unindexed_notes.txt",
            storage_key="documents/draft_unindexed_notes.txt",
            content_type="text/plain",
            file_size=400,
            checksum="checksum_doc_pending",
            uploader_id=user_a.id,
            status=DocumentStatus.PROCESSING,
        )
        session.add_all([doc_a, doc_b, doc_pending])
        await session.commit()
        await session.refresh(doc_a)
        await session.refresh(doc_b)
        await session.refresh(doc_pending)

        u_a_id = user_a.id
        u_b_id = user_b.id
        adm_id = admin.id
        d_a_id = doc_a.id
        d_b_id = doc_b.id
        d_pending_id = doc_pending.id

    # Index doc_a and doc_b using IndexingService
    embedding_provider = DeterministicEmbeddingProvider(dimensions=128)
    indexing = IndexingService(
        splitter=TextSplitter(ChunkingConfig(chunk_size=150, chunk_overlap=20)),
        provider=embedding_provider,
    )

    async with session_factory() as session:
        await indexing.index_document(
            session=session,
            document_id=d_a_id,
            text=(
                "Quantum computing uses qubits capable of superposition to perform complex calculations. "
                "Quantum superposition enables exponential processing speedups for specific algorithms."
            ),
        )
        await indexing.index_document(
            session=session,
            document_id=d_b_id,
            text=(
                "Q3 financial results reported revenue growth of 24 percent year over year. "
                "Operating cash flows exceeded expectations driven by subscription expansions."
            ),
        )


    yield session_factory, u_a_id, u_b_id, adm_id, d_a_id, d_b_id, d_pending_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_r001_relevant_query_retrieves_chunks_and_generates_grounded_answer(rag_test_db):
    """R001: Relevant query retrieves relevant fixture chunks and generates grounded answer."""
    session_factory, u_a_id, _, _, d_a_id, _, _ = rag_test_db

    indexing = IndexingService(provider=DeterministicEmbeddingProvider(dimensions=128))
    llm = DeterministicLlmProvider()
    rag_service = RagService(indexing_service=indexing, llm_provider=llm)

    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        req = RagQueryRequest(query="qubits quantum computing superposition", limit=3, similarity_threshold=0.10)
        answer = await rag_service.answer_query(session, user_a, req)

        assert answer.insufficient_evidence is False
        assert answer.retrieved_chunks_count > 0
        assert len(answer.citations) > 0
        assert "superposition" in answer.answer.lower() or "quantum" in answer.answer.lower()


@pytest.mark.asyncio
async def test_r002_r007_no_match_query_produces_insufficient_evidence_with_no_fabricated_citations(rag_test_db):
    """R002 & R007: No-match query produces explicit insufficient evidence and fabricates zero citations."""
    session_factory, u_a_id, _, _, _, _, _ = rag_test_db

    indexing = IndexingService(provider=DeterministicEmbeddingProvider(dimensions=128))
    llm = DeterministicLlmProvider()
    rag_service = RagService(indexing_service=indexing, llm_provider=llm)

    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        # Search query completely unrelated to user A's document (quantum computing) with high similarity threshold
        req = RagQueryRequest(
            query="photosynthesis chlorophyll sunlight plant chloroplasts",
            limit=3,
            similarity_threshold=0.95,
        )
        answer = await rag_service.answer_query(session, user_a, req)

        assert answer.insufficient_evidence is True
        assert INSUFFICIENT_EVIDENCE_ANSWER in answer.answer
        # No citations must be fabricated (R007)
        assert len(answer.citations) == 0
        assert answer.retrieved_chunks_count == 0


@pytest.mark.asyncio
async def test_r003_query_embedding_failure_is_handled_safely(rag_test_db):
    """R003: Query embedding failure is handled safely."""
    session_factory, u_a_id, _, _, _, _, _ = rag_test_db

    class FailingEmbeddingProvider(DeterministicEmbeddingProvider):
        async def embed_query(self, query: str):
            raise RuntimeError("Embedding model endpoint connection failure")

    indexing = IndexingService(provider=FailingEmbeddingProvider(dimensions=128))
    rag_service = RagService(indexing_service=indexing, llm_provider=DeterministicLlmProvider())

    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        req = RagQueryRequest(query="test query")
        with pytest.raises(RuntimeError, match="Embedding model endpoint connection failure"):
            await rag_service.answer_query(session, user_a, req)


@pytest.mark.asyncio
async def test_r006_every_citation_maps_to_a_retrieved_chunk(rag_test_db):
    """R006: Every citation maps to an actual retrieved document and chunk."""
    session_factory, u_a_id, _, _, d_a_id, _, _ = rag_test_db

    indexing = IndexingService(provider=DeterministicEmbeddingProvider(dimensions=128))
    rag_service = RagService(indexing_service=indexing, llm_provider=DeterministicLlmProvider())

    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        req = RagQueryRequest(query="quantum computing qubits", limit=2, similarity_threshold=0.10)
        answer = await rag_service.answer_query(session, user_a, req)

        assert len(answer.citations) > 0
        for citation in answer.citations:
            assert citation.document_id == d_a_id
            assert citation.document_title == "quantum_computing_guide.txt"
            assert citation.chunk_index >= 0
            assert citation.relevance_score > 0.0
            assert len(citation.snippet) > 0


@pytest.mark.asyncio
async def test_r010_unauthorized_documents_excluded_before_llm_context(rag_test_db):
    """R010: Unauthorized documents are excluded before LLM context construction."""
    session_factory, u_a_id, u_b_id, adm_id, d_a_id, d_b_id, _ = rag_test_db

    indexing = IndexingService(provider=DeterministicEmbeddingProvider(dimensions=128))
    rag_service = RagService(indexing_service=indexing, llm_provider=DeterministicLlmProvider())

    # User A searches for Q3 financial results (owned by User B)
    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        req = RagQueryRequest(query="Q3 financial results revenue growth", limit=5, similarity_threshold=0.10)
        answer_a = await rag_service.answer_query(session, user_a, req)

        # User A must NOT retrieve User B's financial document
        assert not any(c.document_id == d_b_id for c in answer_a.citations)

    # Admin searches for Q3 financial results -> Allowed because Admin has access across deployment
    async with session_factory() as session:
        admin = await session.get(User, adm_id)
        req = RagQueryRequest(query="Q3 financial results revenue growth", limit=5, similarity_threshold=0.10)
        answer_admin = await rag_service.answer_query(session, admin, req)

        assert any(c.document_id == d_b_id for c in answer_admin.citations)


@pytest.mark.asyncio
async def test_r011_unindexed_and_non_ready_documents_are_not_retrieved(rag_test_db):
    """R011: Documents with status != READY are excluded from retrieval."""
    session_factory, u_a_id, _, _, _, _, d_pending_id = rag_test_db

    indexing = IndexingService(provider=DeterministicEmbeddingProvider(dimensions=128))
    rag_service = RagService(indexing_service=indexing, llm_provider=DeterministicLlmProvider())

    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        # Search query for pending doc content
        req = RagQueryRequest(query="draft unindexed notes", limit=5, similarity_threshold=0.01)
        answer = await rag_service.answer_query(session, user_a, req)

        # Pending document must never appear in citations
        assert not any(c.document_id == d_pending_id for c in answer.citations)


@pytest.mark.asyncio
async def test_r017_usage_and_latency_metadata_safely_recorded(rag_test_db):
    """R017: Usage and latency metadata is safely recorded."""
    session_factory, u_a_id, _, _, _, _, _ = rag_test_db

    indexing = IndexingService(provider=DeterministicEmbeddingProvider(dimensions=128))
    rag_service = RagService(indexing_service=indexing, llm_provider=DeterministicLlmProvider())

    async with session_factory() as session:
        user_a = await session.get(User, u_a_id)
        req = RagQueryRequest(query="quantum computing superposition", limit=2, similarity_threshold=0.10)
        answer = await rag_service.answer_query(session, user_a, req)

        assert answer.latency_ms > 0.0
        assert answer.usage is not None
        assert answer.usage.total_tokens > 0
        assert answer.model == "deterministic-llm-v1"
