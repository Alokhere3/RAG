"""Integration tests for Phase 5 Vector Indexing & Similarity Search (E012-E017)."""

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import IncompatibleModelError, NotFoundError
from app.db.base import Base
from app.models.chunk import DocumentChunk, VectorIndexMetadata
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole, UserStatus
from app.services.chunking import ChunkingConfig, TextSplitter
from app.services.embeddings.deterministic import DeterministicEmbeddingProvider
from app.services.indexing_service import IndexingService, cosine_similarity
from app.services.parsers.base import PageContent


@pytest.fixture
async def index_test_db(tmp_path):
    """Isolated SQLite database fixture for vector indexing tests."""
    db_file = tmp_path / "test_indexing.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Seed test user and document
    async with session_factory() as session:
        user = User(
            email="researcher@example.com",
            password_hash="argon2id$mockhash",
            display_name="Researcher",
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        doc = Document(
            filename="rag_paper.txt",
            storage_key="documents/rag_paper.txt",
            content_type="text/plain",
            file_size=500,
            checksum="samplechecksum1234567890",
            uploader_id=user.id,
            status=DocumentStatus.UPLOADED,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        doc_id = doc.id
        user_id = user.id

    yield session_factory, doc_id, user_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_e012_duplicate_ingestion_does_not_duplicate_chunks(index_test_db):
    """E012: Duplicate ingestion does not duplicate index records."""
    session_factory, doc_id, _ = index_test_db
    provider = DeterministicEmbeddingProvider(dimensions=128)
    service = IndexingService(provider=provider)

    sample_text = "First paragraph of document.\n\nSecond paragraph detailing components.\n\nThird paragraph."

    async with session_factory() as session:
        # First index run
        chunks_1 = await service.index_document(session, doc_id, sample_text)
        assert len(chunks_1) > 0

    async with session_factory() as session:
        res = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
        count_first = len(res.scalars().all())

        # Second index run with the same document
        chunks_2 = await service.index_document(session, doc_id, sample_text)
        assert len(chunks_2) == len(chunks_1)

    async with session_factory() as session:
        res = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
        all_chunks = res.scalars().all()
        # Chunks must be replaced, not doubled
        assert len(all_chunks) == count_first


@pytest.mark.asyncio
async def test_e013_reindexing_preserves_consistency(index_test_db):
    """E013: Re-indexing updates chunks consistently and cleans up old records."""
    session_factory, doc_id, _ = index_test_db
    provider = DeterministicEmbeddingProvider(dimensions=128)
    service = IndexingService(provider=provider)

    text_v1 = "Initial text content that gets chunked into version one."
    text_v2 = "Completely updated new text for version two."

    async with session_factory() as session:
        await service.index_document(session, doc_id, text_v1)

    async with session_factory() as session:
        chunks_v2 = await service.index_document(session, doc_id, text_v2)
        assert any("version two" in c.content for c in chunks_v2)

    async with session_factory() as session:
        res = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
        stored = res.scalars().all()
        # Old text must not be present
        assert not any("version one" in c.content for c in stored)
        assert any("version two" in c.content for c in stored)


@pytest.mark.asyncio
async def test_e014_partial_batch_failure_rolls_back(index_test_db):
    """E014: Partial batch failure is not marked complete incorrectly."""
    session_factory, doc_id, _ = index_test_db

    class FailingProvider(DeterministicEmbeddingProvider):
        async def embed_texts(self, texts):
            raise RuntimeError("Network failure mid-batch")

    service = IndexingService(provider=FailingProvider(dimensions=128))

    async with session_factory() as session:
        with pytest.raises(RuntimeError, match="Network failure mid-batch"):
            await service.index_document(session, doc_id, "Test text content for indexing")

    # Verify no partial chunks were committed
    async with session_factory() as session:
        res = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
        assert len(res.scalars().all()) == 0


@pytest.mark.asyncio
async def test_e015_similarity_search_retrieves_relevant_chunks(index_test_db):
    """E015: Vector similarity search returns ranked results."""
    session_factory, doc_id, _ = index_test_db
    provider = DeterministicEmbeddingProvider(dimensions=128)
    splitter = TextSplitter(ChunkingConfig(chunk_size=100, chunk_overlap=20))
    service = IndexingService(splitter=splitter, provider=provider)

    doc_text = (
        "Quantum computing relies on qubits to perform computations exponentially faster.\n\n"
        "Machine learning algorithms train on massive datasets to identify patterns.\n\n"
        "Photosynthesis allows green plants to convert sunlight into chemical energy."
    )

    async with session_factory() as session:
        await service.index_document(session, doc_id, doc_text)

    async with session_factory() as session:
        # Search for quantum computing
        results = await service.search_similar(session, "qubits quantum computing", limit=2)

        assert len(results) > 0
        top_chunk, score = results[0]
        assert "Quantum" in top_chunk.content or "qubits" in top_chunk.content
        assert score > 0.0


@pytest.mark.asyncio
async def test_e016_model_change_cannot_mix_incompatible_vectors(index_test_db):
    """E016: Model change cannot silently mix incompatible vectors."""
    session_factory, doc_id, _ = index_test_db

    # Initialize index with model A (128d)
    service_a = IndexingService(
        provider=DeterministicEmbeddingProvider(model_name="model-a-128", dimensions=128)
    )

    async with session_factory() as session:
        await service_a.index_document(session, doc_id, "Document indexed with model A.")

    # Attempt to index with incompatible model B (384d)
    service_b = IndexingService(
        provider=DeterministicEmbeddingProvider(model_name="model-b-384", dimensions=384)
    )

    async with session_factory() as session:
        with pytest.raises(IncompatibleModelError, match="Active vector index uses model 'model-a-128'"):
            await service_b.index_document(session, doc_id, "Attempting index with model B.")


@pytest.mark.asyncio
async def test_e017_document_deletion_cascades_chunks(index_test_db):
    """E017: Document deletion removes associated chunks/vectors."""
    session_factory, doc_id, _ = index_test_db
    provider = DeterministicEmbeddingProvider(dimensions=128)
    service = IndexingService(provider=provider)

    async with session_factory() as session:
        await service.index_document(session, doc_id, "Document content to be deleted.")

    async with session_factory() as session:
        # Verify chunks exist
        res = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
        assert len(res.scalars().all()) > 0

        # Delete document index via service
        deleted = await service.delete_document_index(session, doc_id)
        assert deleted > 0

    async with session_factory() as session:
        # Verify chunks are gone
        res = await session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
        assert len(res.scalars().all()) == 0
