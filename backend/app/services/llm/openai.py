"""OpenAI chat completion provider adapter with retry, rate limit handling, and output validation."""

import asyncio
import logging
from typing import List, Optional

import httpx

from app.core.errors import (
    LlmRateLimitError,
    LlmTimeoutError,
    MalformedLlmOutputError,
    MissingLlmKeyError,
)
from app.services.llm.base import (
    BaseLlmProvider,
    LlmMessage,
    LlmResponse,
    LlmUsage,
)

logger = logging.getLogger(__name__)


class OpenAILlmProvider(BaseLlmProvider):
    """Adapter for OpenAI chat completions API endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
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
    def is_external(self) -> bool:
        return True

    def _validate_api_key(self) -> str:
        if not self._api_key or not self._api_key.strip():
            raise MissingLlmKeyError("OpenAI API key is missing or unset.")
        masked = f"{self._api_key[:4]}...{self._api_key[-4:]}" if len(self._api_key) > 8 else "***"
        logger.info("OPENAI_LLM_PROVIDER_INITIALIZED model=%s key=%s", self._model, masked)
        return self._api_key

    async def generate(
        self,
        messages: List[LlmMessage],
        max_tokens: Optional[int] = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        key = self._validate_api_key()
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

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
                    logger.warning("OPENAI_LLM_RATE_LIMITED attempt=%d/%d backoff=%.2fs", attempts, self._max_retries, backoff)
                    if attempts >= self._max_retries:
                        raise LlmRateLimitError("OpenAI LLM rate limit exceeded after maximum retries.")
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
                    if resp.status_code == 429:
                        raise LlmRateLimitError(err_msg)
                    raise LlmTimeoutError(err_msg)

                data = resp.json()
                choices = data.get("choices", [])
                if not choices or not isinstance(choices, list):
                    raise MalformedLlmOutputError("OpenAI response contains no choices.")

                first_choice = choices[0]
                message_dict = first_choice.get("message", {})
                content = message_dict.get("content")
                if content is None:
                    raise MalformedLlmOutputError("OpenAI response message contains no text content.")

                usage_dict = data.get("usage", {})
                usage = LlmUsage(
                    prompt_tokens=usage_dict.get("prompt_tokens", 0),
                    completion_tokens=usage_dict.get("completion_tokens", 0),
                    total_tokens=usage_dict.get("total_tokens", 0),
                )

                finish_reason = first_choice.get("finish_reason")

                return LlmResponse(
                    content=content,
                    model=data.get("model", self._model),
                    usage=usage,
                    finish_reason=finish_reason,
                )

            except httpx.TimeoutException:
                logger.warning("OPENAI_LLM_TIMEOUT attempt=%d/%d", attempts, self._max_retries)
                if attempts >= self._max_retries:
                    raise LlmTimeoutError(f"OpenAI LLM request timed out after {self._max_retries} attempts.")
                await asyncio.sleep(backoff)
                backoff *= 2.0

            except (MissingLlmKeyError, LlmRateLimitError, MalformedLlmOutputError):
                raise

            except Exception as exc:
                if attempts >= self._max_retries:
                    raise LlmTimeoutError(f"OpenAI LLM request failed: {type(exc).__name__}")
                await asyncio.sleep(backoff)
                backoff *= 2.0

        raise LlmTimeoutError("Exceeded retry budget communicating with OpenAI LLM.")
