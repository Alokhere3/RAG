"""OpenAI embedding provider adapter with retry, rate limit handling, and dimension validation."""

import asyncio
import logging
from typing import List, Optional

import httpx

from app.core.errors import (
    DimensionMismatchError,
    MissingProviderKeyError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.services.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingBatchResult,
    EmbeddingVector,
)

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """Adapter for OpenAI embedding API endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client = http_client

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def is_external(self) -> bool:
        return True

    def _validate_api_key(self) -> str:
        if not self._api_key or not self._api_key.strip():
            raise MissingProviderKeyError("OpenAI API key is missing or unset.")
        masked = f"{self._api_key[:4]}...{self._api_key[-4:]}" if len(self._api_key) > 8 else "***"
        logger.info("OPENAI_PROVIDER_INITIALIZED model=%s key=%s", self._model, masked)
        return self._api_key


    async def embed_texts(self, texts: List[str]) -> EmbeddingBatchResult:
        if not texts:
            return EmbeddingBatchResult(
                embeddings=[],
                model=self._model,
                dimensions=self._dimensions,
                total_tokens=0,
            )

        key = self._validate_api_key()
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "input": texts,
            "dimensions": self._dimensions,
        }

        attempts = 0
        backoff = 0.2

        while attempts < self._max_retries:
            attempts += 1
            try:
                if self._client:
                    resp = await self._client.post(url, json=payload, headers=headers, timeout=self._timeout_seconds)
                else:
                    async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                        resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 429:
                    logger.warning("OPENAI_RATE_LIMITED attempt=%d/%d backoff=%.2fs", attempts, self._max_retries, backoff)
                    if attempts >= self._max_retries:
                        raise ProviderRateLimitError("OpenAI rate limit exceeded after maximum retries.")
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                    continue

                if resp.status_code >= 400:
                    err_msg = f"OpenAI API error: HTTP {resp.status_code}"
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", {}).get("message", err_msg)
                    except Exception:
                        pass
                    raise ProviderRateLimitError(err_msg) if resp.status_code == 429 else ProviderTimeoutError(err_msg)

                data = resp.json()
                raw_embeddings = data.get("data", [])
                vectors: List[EmbeddingVector] = [item["embedding"] for item in raw_embeddings]

                # Validate dimensions for every returned vector
                for idx, vec in enumerate(vectors):
                    if len(vec) != self._dimensions:
                        raise DimensionMismatchError(
                            f"Vector at index {idx} has dimension {len(vec)}, expected {self._dimensions}"
                        )

                total_tokens = data.get("usage", {}).get("total_tokens", 0)

                return EmbeddingBatchResult(
                    embeddings=vectors,
                    model=self._model,
                    dimensions=self._dimensions,
                    total_tokens=total_tokens,
                )

            except httpx.TimeoutException as exc:
                logger.warning("OPENAI_TIMEOUT attempt=%d/%d", attempts, self._max_retries)
                if attempts >= self._max_retries:
                    raise ProviderTimeoutError(f"OpenAI embedding request timed out after {self._max_retries} attempts.")
                await asyncio.sleep(backoff)
                backoff *= 2.0

            except (DimensionMismatchError, MissingProviderKeyError, ProviderRateLimitError):
                raise

            except Exception as exc:
                if attempts >= self._max_retries:
                    raise ProviderTimeoutError(f"OpenAI request failed: {type(exc).__name__}")
                await asyncio.sleep(backoff)
                backoff *= 2.0

        raise ProviderTimeoutError("Exceeded retry budget communicating with OpenAI.")

    async def embed_query(self, query: str) -> EmbeddingVector:
        result = await self.embed_texts([query])
        if not result.embeddings:
            raise DimensionMismatchError("Received empty embeddings for query.")
        return result.embeddings[0]
