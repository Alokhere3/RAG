"""Abstract base interface and data transfer objects for embedding providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

EmbeddingVector = List[float]


@dataclass(frozen=True)
class EmbeddingBatchResult:
    """Result of embedding a batch of texts."""

    embeddings: List[EmbeddingVector]
    model: str
    dimensions: int
    total_tokens: int = 0


class BaseEmbeddingProvider(ABC):
    """Abstract contract for all embedding models and providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'openai', 'deterministic', 'ollama')."""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """Specific model name (e.g. 'text-embedding-3-small', 'deterministic-384')."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Output embedding vector dimensionality."""
        pass

    @property
    @abstractmethod
    def is_external(self) -> bool:
        """True if data egresses outside the deployment infrastructure."""
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> EmbeddingBatchResult:
        """Generate vector embeddings for a batch of text chunks."""
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> EmbeddingVector:
        """Generate a vector embedding for a single search query."""
        pass
