"""Indexing service managing document chunking, vector generation, and index consistency."""

import hashlib
import logging
import math
from typing import Any, Dict, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    DimensionMismatchError,
    IncompatibleModelError,
    NotFoundError,
)
from app.models.chunk import DocumentChunk, VectorIndexMetadata
from app.models.document import Document, DocumentStatus
from app.services.chunking import Chunk, ChunkingConfig, TextSplitter
from app.services.embeddings import (
    BaseEmbeddingProvider,
    create_embedding_provider,
)
from app.services.parsers.base import PageContent, ParseResult

logger = logging.getLogger(__name__)


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two unit- or non-unit-normalized vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class IndexingService:
    """Orchestrates document chunking, batch vector embedding, and persistent storage."""

    def __init__(
        self,
        splitter: Optional[TextSplitter] = None,
        provider: Optional[BaseEmbeddingProvider] = None,
        batch_size: int = 50,
    ) -> None:
        self.splitter = splitter or TextSplitter(ChunkingConfig())
        self.provider = provider or create_embedding_provider()
        self.batch_size = max(1, batch_size)

    async def ensure_index_metadata(self, session: AsyncSession) -> VectorIndexMetadata:
        """Validate or initialize active index metadata; prevent silent model mixing (E016)."""
        stmt = (
            select(VectorIndexMetadata)
            .where(VectorIndexMetadata.is_active.is_(True))
            .order_by(VectorIndexMetadata.created_at.desc())
        )
        res = await session.execute(stmt)
        active_meta = res.scalars().first()

        current_model = self.provider.model
        current_dims = self.provider.dimensions
        current_version = self.splitter.config.version

        if not active_meta:
            new_meta = VectorIndexMetadata(
                model_name=current_model,
                dimensions=current_dims,
                chunking_version=current_version,
                index_version=1,
                is_active=True,
            )
            session.add(new_meta)
            await session.commit()
            await session.refresh(new_meta)
            logger.info(
                "INDEX_METADATA_INITIALIZED model=%s dims=%d version=%s",
                current_model,
                current_dims,
                current_version,
            )
            return new_meta

        # Enforce incompatibility guard (E016)
        if active_meta.model_name != current_model or active_meta.dimensions != current_dims:
            logger.error(
                "INCOMPATIBLE_MODEL_DETECTED active_model=%s active_dims=%d requested_model=%s requested_dims=%d",
                active_meta.model_name,
                active_meta.dimensions,
                current_model,
                current_dims,
            )
            raise IncompatibleModelError(
                f"Active vector index uses model '{active_meta.model_name}' ({active_meta.dimensions}d), "
                f"which cannot be mixed with '{current_model}' ({current_dims}d)."
            )

        return active_meta

    async def index_document(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        text: str,
        pages: Optional[List[PageContent]] = None,
    ) -> List[DocumentChunk]:
        """Atomically chunk, embed, and store document chunks in the vector store."""
        # 1. Verify document existence
        doc_stmt = select(Document).where(Document.id == document_id)
        doc_res = await session.execute(doc_stmt)
        document = doc_res.scalar_one_or_none()

        if not document:
            raise NotFoundError(f"Document '{document_id}' not found.")

        if document.status == DocumentStatus.DELETED:
            raise NotFoundError(f"Document '{document_id}' has been deleted.")

        # 2. Check and enforce active index metadata
        await self.ensure_index_metadata(session)

        # 3. Deterministic chunking
        if pages:
            parse_result = ParseResult(
                text=text,
                page_count=len(pages),
                char_count=len(text),
                parser_name="pre-extracted",
                parser_version="1.0",
                pages=pages,
            )
            raw_chunks = self.splitter.split_parse_result(parse_result)
        else:
            raw_chunks = self.splitter.split_text(text)

        if not raw_chunks:
            logger.info("INDEXING_EMPTY_TEXT doc_id=%s chunks=0", document_id)
            return []

        logger.info(
            "INDEXING_STARTED doc_id=%s raw_chunks=%d model=%s dims=%d",
            document_id,
            len(raw_chunks),
            self.provider.model,
            self.provider.dimensions,
        )

        # 4. Batch embedding generation with failure bounding (E014)
        all_embeddings: List[List[float]] = []
        for i in range(0, len(raw_chunks), self.batch_size):
            batch = raw_chunks[i : i + self.batch_size]
            batch_texts = [c.text for c in batch]
            result = await self.provider.embed_texts(batch_texts)

            if len(result.embeddings) != len(batch):
                raise DimensionMismatchError(
                    f"Expected {len(batch)} vectors for batch {i}, received {len(result.embeddings)}"
                )

            all_embeddings.extend(result.embeddings)

        # 5. Atomic persistence: replace existing chunks for this document (E012, E013)
        await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

        persisted_chunks: List[DocumentChunk] = []
        for chunk, emb in zip(raw_chunks, all_embeddings):
            checksum = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            db_chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.index,
                content=chunk.text,
                char_count=chunk.char_count,
                token_count=len(chunk.text.split()),
                page_number=chunk.page_number,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                embedding=emb,
                embedding_model=self.provider.model,
                embedding_dimensions=self.provider.dimensions,
                checksum=checksum,
                metadata_json=chunk.metadata,
            )
            session.add(db_chunk)
            persisted_chunks.append(db_chunk)

        # 6. Mark document as READY upon successful indexing
        document.status = DocumentStatus.READY
        await session.commit()

        logger.info(
            "INDEXING_COMPLETED doc_id=%s indexed_chunks=%d",
            document_id,
            len(persisted_chunks),
        )
        return persisted_chunks

    async def delete_document_index(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
    ) -> int:
        """Remove all chunks associated with a deleted document (E017)."""
        res = await session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        await session.commit()
        deleted_count = res.rowcount or 0
        logger.info("DOCUMENT_INDEX_DELETED doc_id=%s chunks_removed=%d", document_id, deleted_count)
        return deleted_count

    async def search_similar(
        self,
        session: AsyncSession,
        query: str,
        limit: int = 5,
        document_ids: Optional[List[uuid.UUID]] = None,
    ) -> List[Tuple[DocumentChunk, float]]:
        """Retrieve most similar chunks to query text using vector cosine similarity (E015)."""
        if not query or not query.strip():
            return []

        query_vec = await self.provider.embed_query(query.strip())
        bind = session.bind
        dialect_name = bind.dialect.name if bind else "sqlite"

        # Check PostgreSQL native pgvector support
        if dialect_name == "postgresql":
            # Native pgvector cosine distance operator: <=>
            stmt = select(DocumentChunk).order_by(
                DocumentChunk.embedding.cosine_distance(query_vec)
            )
            if document_ids:
                stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
            stmt = stmt.limit(limit)

            res = await session.execute(stmt)
            chunks = res.scalars().all()
            # Return with calculated similarity
            results = []
            for c in chunks:
                sim = cosine_similarity(query_vec, c.embedding) if c.embedding else 0.0
                results.append((c, sim))
            return results

        # SQLite fallback (in-memory candidate similarity calculation)
        stmt = select(DocumentChunk)
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        res = await session.execute(stmt)
        all_chunks = res.scalars().all()

        scored_chunks: List[Tuple[DocumentChunk, float]] = []
        for c in all_chunks:
            if c.embedding:
                sim = cosine_similarity(query_vec, c.embedding)
                scored_chunks.append((c, sim))

        # Sort descending by similarity
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        return scored_chunks[:limit]


indexing_service = IndexingService()
