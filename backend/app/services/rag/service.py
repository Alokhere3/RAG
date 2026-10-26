"""RAG Core orchestration service: authorized retrieval, context budgeting, and grounded generation."""

import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.models.chunk import DocumentChunk
from app.services.indexing_service import IndexingService, indexing_service as default_indexing_service
from app.services.llm.base import BaseLlmProvider
from app.services.llm.registry import get_default_llm_provider
from app.services.rag.citation import (
    extract_citation_snippet,
    extract_claims_for_chunk,
)
from app.services.rag.prompt import RagPromptBuilder
from app.services.rag.schemas import Citation, RagAnswer, RagQueryRequest

logger = logging.getLogger(__name__)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "I cannot answer this question because the provided documents do not contain sufficient evidence."
)


class RagService:
    """Core RAG engine managing retrieval authorization, context assembly, and LLM grounding."""

    def __init__(
        self,
        indexing_service: Optional[IndexingService] = None,
        llm_provider: Optional[BaseLlmProvider] = None,
        prompt_builder: Optional[RagPromptBuilder] = None,
    ) -> None:
        self._indexing = indexing_service or default_indexing_service
        self._llm = llm_provider or get_default_llm_provider()
        self._prompt_builder = prompt_builder or RagPromptBuilder()

    @property
    def indexing_service(self) -> IndexingService:
        return self._indexing

    @property
    def llm_provider(self) -> BaseLlmProvider:
        return self._llm

    async def get_authorized_document_map(
        self,
        session: AsyncSession,
        user: User,
    ) -> Dict[uuid.UUID, str]:
        """Query all READY documents accessible to the requesting user."""
        stmt = select(Document.id, Document.filename).where(
            Document.status == DocumentStatus.READY
        )

        # Non-admin users can only retrieve chunks from their own uploaded documents
        if user.role != UserRole.ADMIN:
            stmt = stmt.where(Document.uploader_id == user.id)


        res = await session.execute(stmt)
        return {row[0]: row[1] for row in res.all()}

    async def retrieve_authorized_chunks(
        self,
        session: AsyncSession,
        user: User,
        query: str,
        limit: int = 5,
        similarity_threshold: float = 0.20,
    ) -> List[Tuple[DocumentChunk, float, str]]:
        """Retrieve and rank chunks strictly constrained to the user's authorized documents."""
        # 1. Fetch authorized documents (R010, R011)
        doc_map = await self.get_authorized_document_map(session, user)
        if not doc_map:
            logger.debug("RETRIEVAL_NO_AUTHORIZED_DOCS user_id=%s", user.id)
            return []

        # 2. Vector similarity search constrained to authorized document IDs
        candidate_results = await self._indexing.search_similar(
            session=session,
            query=query,
            limit=limit * 2,  # Over-fetch slightly for threshold and dedup filtering
            document_ids=list(doc_map.keys()),
        )

        # 3. Filter by similarity threshold
        filtered_results: List[Tuple[DocumentChunk, float, str]] = []
        for chunk, score in candidate_results:
            if score >= similarity_threshold:
                doc_title = doc_map.get(chunk.document_id, "Document")
                # Attach convenience attributes for prompt packaging
                chunk.document_title = doc_title  # type: ignore[attr-defined]
                chunk.similarity_score = score  # type: ignore[attr-defined]
                filtered_results.append((chunk, score, doc_title))

        return filtered_results[:limit]

    async def answer_query(
        self,
        session: AsyncSession,
        user: User,
        request: RagQueryRequest,
    ) -> RagAnswer:
        """Execute end-to-end RAG pipeline: retrieval -> grounding -> citation generation."""
        start_time = time.perf_counter()
        query_text = request.query.strip()

        # 1. Retrieve authorized chunks
        retrieved_tuples = await self.retrieve_authorized_chunks(
            session=session,
            user=user,
            query=query_text,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold,
        )

        # 2. Check for weak/no evidence (R002, R007)
        if not retrieved_tuples:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info("RAG_INSUFFICIENT_EVIDENCE query_len=%d latency_ms=%.2f", len(query_text), elapsed_ms)
            return RagAnswer(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                citations=[],
                insufficient_evidence=True,
                retrieved_chunks_count=0,
                latency_ms=elapsed_ms,
                usage=None,
                model=self._llm.model,
            )

        chunks = [t[0] for t in retrieved_tuples]

        # 3. Assemble prompt with injection fencing and context budgeting (R005, R008, R009, R012)
        messages, packed_chunks = self._prompt_builder.build_prompt_messages(
            query=query_text,
            chunks=chunks,
        )

        # 4. Generate grounded completion (R004, R013)
        llm_response = await self._llm.generate(messages)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        raw_answer = llm_response.content.strip()

        # 5. Determine if answer indicates insufficient evidence
        is_insufficient = (
            "insufficient evidence" in raw_answer.lower()
            or "cannot answer this question" in raw_answer.lower()
        )

        # 6. Build verified citations strictly for chunks included in context (R006, R007)
        citations: List[Citation] = []
        if not is_insufficient:
            for chunk in packed_chunks:
                score = getattr(chunk, "similarity_score", 1.0)
                title = getattr(chunk, "document_title", "Document")
                chunk_claims = extract_claims_for_chunk(raw_answer, chunk.chunk_index)
                claim_context = " ".join(chunk_claims) if chunk_claims else ""
                snippet, start_offset, end_offset = extract_citation_snippet(
                    content=chunk.content,
                    query=query_text,
                    answer=raw_answer,
                    claim=claim_context,
                )
                citations.append(
                    Citation(
                        document_id=chunk.document_id,
                        document_title=title,
                        chunk_id=chunk.id,
                        chunk_index=chunk.chunk_index,
                        relevance_score=round(float(score), 4),
                        snippet=snippet,
                        char_offset_start=start_offset,
                        char_offset_end=end_offset,
                    )
                )

        logger.info(
            "RAG_QUERY_COMPLETED user_id=%s retrieved=%d citations=%d latency_ms=%.2f",
            user.id,
            len(retrieved_tuples),
            len(citations),
            elapsed_ms,
        )

        return RagAnswer(
            answer=raw_answer,
            citations=citations,
            insufficient_evidence=is_insufficient,
            retrieved_chunks_count=len(retrieved_tuples),
            latency_ms=elapsed_ms,
            usage=llm_response.usage,
            model=llm_response.model,
        )
