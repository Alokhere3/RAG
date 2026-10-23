"""Unit tests for embedding providers covering E006-E011."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.errors import (
    DimensionMismatchError,
    MissingProviderKeyError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from app.services.embeddings.deterministic import DeterministicEmbeddingProvider
from app.services.embeddings.openai import OpenAIEmbeddingProvider
from app.services.embeddings.registry import create_embedding_provider


@pytest.mark.asyncio
async def test_e006_provider_returns_expected_vector_shape():
    """E006: Embedding provider success returns expected vector shape."""
    provider = DeterministicEmbeddingProvider(dimensions=384)
    assert provider.dimensions == 384
    assert provider.is_external is False

    texts = ["First test sentence.", "Second test chunk with different length."]
    result = await provider.embed_texts(texts)

    assert len(result.embeddings) == 2
    for vec in result.embeddings:
        assert len(vec) == 384
        # Assert normalized L2 norm is ~ 1.0
        norm = sum(x * x for x in vec)
        assert abs(norm - 1.0) < 1e-4

    query_vec = await provider.embed_query("Search query")
    assert len(query_vec) == 384


@pytest.mark.asyncio
async def test_e007_provider_timeout_and_retry_bounded():
    """E007: Provider timeout/retry is bounded."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

    provider = OpenAIEmbeddingProvider(
        api_key="sk-testkey1234567890",
        dimensions=1536,
        timeout_seconds=0.1,
        max_retries=2,
        http_client=mock_client,
    )

    with pytest.raises(ProviderTimeoutError, match="timed out"):
        await provider.embed_texts(["Test chunk"])

    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_e008_provider_rate_limit_backs_off():
    """E008: Provider rate limiting backs off safely."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # First attempt: 429 Too Many Requests
    resp_429 = httpx.Response(status_code=429, json={"error": {"message": "Rate limit reached"}})
    # Second attempt: 200 OK
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "data": [{"embedding": [0.1] * 1536}],
            "usage": {"total_tokens": 12},
        },
    )
    mock_client.post.side_effect = [resp_429, resp_200]

    provider = OpenAIEmbeddingProvider(
        api_key="sk-testkey1234567890",
        dimensions=1536,
        max_retries=3,
        http_client=mock_client,
    )

    res = await provider.embed_texts(["Chunk after rate limit"])
    assert len(res.embeddings) == 1
    assert len(res.embeddings[0]) == 1536
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_e008_provider_rate_limit_exhausted_raises():
    """E008: Exhausted rate limits raise ProviderRateLimitError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    resp_429 = httpx.Response(status_code=429, json={"error": {"message": "Rate limit exceeded"}})
    mock_client.post.return_value = resp_429

    provider = OpenAIEmbeddingProvider(
        api_key="sk-testkey1234567890",
        dimensions=1536,
        max_retries=2,
        http_client=mock_client,
    )

    with pytest.raises(ProviderRateLimitError):
        await provider.embed_texts(["Chunk"])


@pytest.mark.asyncio
async def test_e009_dimension_mismatch_rejected():
    """E009: Invalid vector dimensions are rejected."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # Model returns 256 dimensions when 1536 is expected
    resp_bad_dim = httpx.Response(
        status_code=200,
        json={
            "data": [{"embedding": [0.5] * 256}],
            "usage": {"total_tokens": 5},
        },
    )
    mock_client.post.return_value = resp_bad_dim

    provider = OpenAIEmbeddingProvider(
        api_key="sk-testkey1234567890",
        dimensions=1536,
        http_client=mock_client,
    )

    with pytest.raises(DimensionMismatchError, match="dimension 256, expected 1536"):
        await provider.embed_texts(["Invalid dimension chunk"])


@pytest.mark.asyncio
async def test_e010_missing_provider_key_gives_clear_error():
    """E010: Missing provider key gives clear safe error."""
    provider = OpenAIEmbeddingProvider(api_key=None)
    with pytest.raises(MissingProviderKeyError, match="API key is missing"):
        await provider.embed_texts(["Chunk"])

    provider_empty = OpenAIEmbeddingProvider(api_key="   ")
    with pytest.raises(MissingProviderKeyError, match="API key is missing"):
        await provider_empty.embed_texts(["Chunk"])


import app.services.embeddings.openai as openai_mod


def test_e011_api_keys_do_not_leak_in_logs_and_repr():
    """E011: API keys do not leak in config/API/logs."""
    raw_key = "sk-live-supersecretstring987654321"

    provider = OpenAIEmbeddingProvider(api_key=raw_key)

    # Check string representations do not leak raw key
    assert raw_key not in repr(provider)
    assert raw_key not in str(provider)

    # Check that logger calls mask the key and never contain raw secret
    with patch.object(openai_mod.logger, "info") as mock_info:
        provider._validate_api_key()
        assert mock_info.called

        for call_args in mock_info.call_args_list:
            args, kwargs = call_args
            for arg in args:
                assert raw_key not in str(arg)
            for v in kwargs.values():
                assert raw_key not in str(v)
            # Verify masked preview is present
            assert any("sk-l...4321" in str(arg) for arg in args)





def test_embedding_factory():
    """Factory correctly creates providers by name."""
    det = create_embedding_provider("deterministic", model="det-model", dimensions=128)
    assert isinstance(det, DeterministicEmbeddingProvider)
    assert det.model == "det-model"
    assert det.dimensions == 128

    oai = create_embedding_provider("openai", model="text-embedding-3-large", dimensions=3072, api_key="sk-test")
    assert isinstance(oai, OpenAIEmbeddingProvider)
    assert oai.model == "text-embedding-3-large"
    assert oai.dimensions == 3072
