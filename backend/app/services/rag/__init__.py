"""RAG Core orchestration package."""

from app.services.rag.citation import (
    extract_citation_snippet,
    validate_chunk_passage_offsets,
)
from app.services.rag.prompt import ContextBudgetManager, RagPromptBuilder, deduplicate_chunks
from app.services.rag.schemas import Citation, RagAnswer, RagQueryRequest
from app.services.rag.service import RagService, INSUFFICIENT_EVIDENCE_ANSWER

__all__ = [
    "ContextBudgetManager",
    "RagPromptBuilder",
    "deduplicate_chunks",
    "Citation",
    "RagAnswer",
    "RagQueryRequest",
    "RagService",
    "INSUFFICIENT_EVIDENCE_ANSWER",
    "extract_citation_snippet",
    "validate_chunk_passage_offsets",
]

