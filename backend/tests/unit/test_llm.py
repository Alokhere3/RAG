"""Unit tests for LLM provider adapters covering R004, R013, R014, R015, R016."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.errors import (
    LlmRateLimitError,
    LlmTimeoutError,
    MalformedLlmOutputError,
    MissingLlmKeyError,
)
from app.services.llm.base import LlmMessage
from app.services.llm.deterministic import DeterministicLlmProvider
from app.services.llm.openai import OpenAILlmProvider
import app.services.llm.openai as openai_llm_mod
from app.services.llm.registry import create_llm_provider


@pytest.mark.asyncio
async def test_r015_deterministic_llm_provider_contract():
    """R015: Deterministic provider adheres to BaseLlmProvider contract."""
    provider = DeterministicLlmProvider(model_name="test-llm")
    assert provider.name == "deterministic"
    assert provider.model == "test-llm"
    assert provider.is_external is False

    messages = [
        LlmMessage(role="system", content="You are a helpful assistant."),
        LlmMessage(role="user", content="Hello world!"),
    ]
    resp = await provider.generate(messages)
    assert resp.model == "test-llm"
    assert resp.usage.total_tokens > 0
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_r004_llm_timeout_is_bounded():
    """R004: LLM timeout is bounded and raises LlmTimeoutError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("Read timed out")

    provider = OpenAILlmProvider(
        api_key="sk-test-key-1234567890",
        timeout_seconds=0.1,
        max_retries=2,
        http_client=mock_client,
    )

    messages = [LlmMessage(role="user", content="Query")]
    with pytest.raises(LlmTimeoutError, match="timed out after 2 attempts"):
        await provider.generate(messages)

    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_r004_llm_rate_limit_backs_off_and_recovers():
    """R004: LLM rate limit (429) retries with backoff and recovers."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    resp_429 = httpx.Response(status_code=429, json={"error": {"message": "Rate limit exceeded"}})
    resp_200 = httpx.Response(
        status_code=200,
        json={
            "model": "gpt-4o-mini",
            "choices": [{"message": {"role": "assistant", "content": "Grounded answer."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )
    mock_client.post.side_effect = [resp_429, resp_200]

    provider = OpenAILlmProvider(
        api_key="sk-test-key-1234567890",
        max_retries=3,
        http_client=mock_client,
    )

    messages = [LlmMessage(role="user", content="Query")]
    resp = await provider.generate(messages)

    assert resp.content == "Grounded answer."
    assert resp.usage.total_tokens == 15
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_r004_llm_rate_limit_exhausted_raises():
    """R004: Exhausted rate limits raise LlmRateLimitError."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    resp_429 = httpx.Response(status_code=429, json={"error": {"message": "Rate limit exceeded"}})
    mock_client.post.return_value = resp_429

    provider = OpenAILlmProvider(
        api_key="sk-test-key-1234567890",
        max_retries=2,
        http_client=mock_client,
    )

    messages = [LlmMessage(role="user", content="Query")]
    with pytest.raises(LlmRateLimitError):
        await provider.generate(messages)


@pytest.mark.asyncio
async def test_r013_malformed_llm_output_rejected():
    """R013: Malformed provider output is validated and rejected."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Empty choices array
    mock_client.post.return_value = httpx.Response(status_code=200, json={"choices": []})

    provider = OpenAILlmProvider(
        api_key="sk-test-key-1234567890",
        http_client=mock_client,
    )

    with pytest.raises(MalformedLlmOutputError, match="contains no choices"):
        await provider.generate([LlmMessage(role="user", content="Query")])


@pytest.mark.asyncio
async def test_r014_missing_provider_key_fails_cleanly():
    """R014: Missing provider key fails clearly without leaking secrets."""
    provider = OpenAILlmProvider(api_key=None)
    with pytest.raises(MissingLlmKeyError, match="API key is missing"):
        await provider.generate([LlmMessage(role="user", content="Query")])

    empty_provider = OpenAILlmProvider(api_key="   ")
    with pytest.raises(MissingLlmKeyError, match="API key is missing"):
        await empty_provider.generate([LlmMessage(role="user", content="Query")])


def test_r014_llm_key_never_leaks_in_logs_and_repr():
    """R014: LLM API key is masked in logs and representation."""
    raw_key = "sk-live-supersecretllmkey987654321"
    provider = OpenAILlmProvider(api_key=raw_key)

    assert raw_key not in repr(provider)
    assert raw_key not in str(provider)

    with patch.object(openai_llm_mod.logger, "info") as mock_info:
        provider._validate_api_key()
        assert mock_info.called
        for call_args in mock_info.call_args_list:
            args, _ = call_args
            for arg in args:
                assert raw_key not in str(arg)
            assert any("sk-l...4321" in str(arg) for arg in args)


def test_r015_factory_creates_providers_by_name():
    """R015: Provider/model selection is configuration-driven."""
    det = create_llm_provider("deterministic", model="custom-det")
    assert isinstance(det, DeterministicLlmProvider)
    assert det.model == "custom-det"

    oai = create_llm_provider("openai", model="gpt-4o", api_key="sk-test")
    assert isinstance(oai, OpenAILlmProvider)
    assert oai.model == "gpt-4o"

    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        create_llm_provider("unsupported-provider-xyz")
