"""Deterministic answer sanitization and normalization for public API boundaries.

Strips internal RAG citation markers such as `[Doc: ..., Chunk: ...]`, `[Chunk: ...]`,
and context packaging tags while strictly preserving:
- Ordinary bracketed text: e.g. `[Note: ...]`, `[RFC 2616]`, `[1]`, `[v1.4]`
- Markdown links: `[label](url)`
- Code syntax and array indexing: `arr[0]`, `matrix[i][j]`
- Legitimate markdown formatting and line breaks
"""

import re
from typing import Optional

# Internal citation markers emitted by the grounding prompt or context packager:
# 1. [Doc: ...] or [Document: ...] or [Source: ...]
# 2. [Chunk: ...] or [Chunks: ...] or [Chunk 123]
# 3. Context envelope tags such as [/Document], [Document (ID: ...)], [Context], [/Context]
# Negative lookahead (?!\() ensures markdown links such as [Document Link](https://...) are preserved.
_CITATION_MARKER_PATTERN = re.compile(
    r"\s*\[\s*(?:\b(?:Doc(?:ument)?|Source)\b\s*[:\s][^\]]*|\bChunks?\b\s*[:\s]?[^\]]*\b\d+[^\]]*|/?\b(?:Document|Context)\b(?:[\s:][^\]]*)?)\s*\](?!\()",
    re.IGNORECASE,
)


def sanitize_answer(text: Optional[str]) -> str:
    """Normalize and sanitize answer text to ensure internal citation markers do not leak.

    Args:
        text: Raw answer string potentially containing internal citation markers.

    Returns:
        Clean, user-facing answer string free of internal citation markers.
    """
    if not text:
        return ""

    # 1. Remove internal citation markers
    sanitized = _CITATION_MARKER_PATTERN.sub("", text)

    # 2. Fix punctuation spacing caused by removing trailing markers (e.g. "word ." -> "word.")
    sanitized = re.sub(r"\s+([.,;:!?])", r"\1", sanitized)

    # 3. Normalize multiple spaces within a line while preserving line breaks
    sanitized = re.sub(r"[^\S\r\n]{2,}", " ", sanitized)

    # 4. Clean trailing whitespace per line and collapse excessive blank lines
    lines = [line.rstrip() for line in sanitized.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        cleaned_lines.append(line)
        prev_blank = is_blank

    return "\n".join(cleaned_lines).strip()
