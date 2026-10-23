"""Deterministic local pseudo-LLM provider for offline testing and verification."""

import re
from typing import Dict, List, Optional

from app.services.llm.base import (
    BaseLlmProvider,
    LlmMessage,
    LlmResponse,
    LlmUsage,
)


class DeterministicLlmProvider(BaseLlmProvider):
    """Deterministic LLM provider used exclusively for testing, CI, and offline benchmarks."""

    def __init__(
        self,
        model_name: str = "deterministic-llm-v1",
        default_response: Optional[str] = None,
        responses_by_keyword: Optional[Dict[str, str]] = None,
        canned_responses: Optional[List[str]] = None,
    ) -> None:
        self._model = model_name
        self._default_response = default_response
        self._responses_by_keyword = responses_by_keyword or {}
        self._canned_responses = list(canned_responses) if canned_responses else []
        self._call_count = 0

    @property
    def name(self) -> str:
        return "deterministic"

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_external(self) -> bool:
        return False

    @property
    def call_count(self) -> int:
        return self._call_count

    async def generate(
        self,
        messages: List[LlmMessage],
        max_tokens: Optional[int] = None,
        temperature: float = 0.0,
    ) -> LlmResponse:
        self._call_count += 1
        prompt_text = " ".join(m.content for m in messages)
        prompt_tokens = sum(len(m.content.split()) for m in messages)

        # 1. Check canned responses queue
        if self._canned_responses:
            answer = self._canned_responses.pop(0)
        # 2. Check keyword overrides
        elif self._match_keyword(prompt_text):
            answer = self._match_keyword(prompt_text)  # type: ignore
        # 3. Check default response
        elif self._default_response is not None:
            answer = self._default_response
        # 4. Synthesize answer from context or declare insufficient evidence
        else:
            answer = self._synthesize_grounded_answer(messages)

        completion_tokens = len(answer.split())
        return LlmResponse(
            content=answer,
            model=self._model,
            usage=LlmUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason="stop",
        )

    def _match_keyword(self, text: str) -> Optional[str]:
        lower = text.lower()
        for kw, resp in self._responses_by_keyword.items():
            if kw.lower() in lower:
                return resp
        return None

    def _synthesize_grounded_answer(self, messages: List[LlmMessage]) -> str:
        """Extract grounded facts from formatted context blocks if present."""
        full_text = " ".join(m.content for m in messages)
        untrusted_text = " ".join(m.content for m in messages if m.role != "system")

        # Detect prompt injection attempts in untrusted content
        if "ignore previous instructions" in untrusted_text.lower() or "disclose deployment secret" in untrusted_text.lower():
            return "I cannot fulfill this request because it violates safety and grounding rules."


        # Find document context blocks formatted as [Document X: ... Chunk Y]
        contexts = re.findall(r"\[Document:\s*([^\n]+)\]([\s\S]*?)\[/Document\]", full_text)
        if not contexts:
            # Check for generic context boundary
            contexts = re.findall(r"<context>([\s\S]*?)</context>", full_text)

        if not contexts or not any(c for c in contexts):
            return "I cannot answer this question because the provided documents do not contain sufficient evidence."

        # Generate a deterministic summary with real citation markers
        snippets = []
        for c in contexts:
            content = c[1] if isinstance(c, tuple) else c
            clean = " ".join(content.strip().split()[:20])
            if clean:
                snippets.append(clean)

        if not snippets:
            return "I cannot answer this question because the provided documents do not contain sufficient evidence."

        return f"Based on the provided documentation: {' '.join(snippets)}."
