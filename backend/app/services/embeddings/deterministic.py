import collections
import functools
import hashlib
import math
import re
from typing import List

from app.services.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingBatchResult,
    EmbeddingVector,
)


@functools.lru_cache(maxsize=16384)
def _compute_word_vector(word: str, dimensions: int) -> List[float]:
    """Compute a cached deterministic pseudo-random vector for a single word."""
    raw = word.encode("utf-8")
    vec: List[float] = []
    for i in range(dimensions):
        h = hashlib.sha256(raw + i.to_bytes(4, byteorder="big")).digest()
        val = int.from_bytes(h[:4], byteorder="big", signed=True) / (2**31)
        vec.append(val)
    return vec


class DeterministicEmbeddingProvider(BaseEmbeddingProvider):
    """Generates deterministic, unit-normalized vectors without external network egress."""

    def __init__(
        self,
        model_name: str = "deterministic-384",
        dimensions: int = 384,
    ) -> None:
        self._model = model_name
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return "deterministic"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def is_external(self) -> bool:
        return False

    async def embed_texts(self, texts: List[str]) -> EmbeddingBatchResult:
        embeddings = [self._compute_vector(t) for t in texts]
        total_tokens = sum(len(t.split()) for t in texts)
        return EmbeddingBatchResult(
            embeddings=embeddings,
            model=self._model,
            dimensions=self._dimensions,
            total_tokens=total_tokens,
        )

    async def embed_query(self, query: str) -> EmbeddingVector:
        return self._compute_vector(query)

    def _compute_vector(self, text: str) -> EmbeddingVector:
        """Compute a unit-normalized vector using word-token aggregation and cryptographic hashes."""
        words = re.findall(r"\w+", text.lower())
        if not words:
            words = ["_empty_"]

        combined = [0.0] * self._dimensions
        counts = collections.Counter(words)

        for word, count in counts.items():
            w_vec = _compute_word_vector(word, self._dimensions)
            weight = 1.0 + math.log(count)
            for i in range(self._dimensions):
                combined[i] += w_vec[i] * weight

        # Normalize to unit length (L2 norm = 1.0)
        norm = math.sqrt(sum(x * x for x in combined))
        if norm > 0:
            combined = [x / norm for x in combined]

        return combined

