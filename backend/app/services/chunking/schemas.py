"""Schemas and configuration for document text chunking."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid


@dataclass(frozen=True)
class Chunk:
    """A deterministic chunk of text extracted from a source document."""

    index: int
    text: str
    char_start: int
    char_end: int
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class ChunkingConfig:
    """Configuration for text chunking algorithms."""

    chunk_size: int = 500
    chunk_overlap: int = 100
    min_chunk_length: int = 10
    strategy: str = "recursive_character"
    version: str = "v1.0"
    separators: List[str] = field(
        default_factory=lambda: ["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""]
    )

    def validate(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {self.chunk_size}")
        if self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap cannot be negative, got {self.chunk_overlap}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be strictly less than chunk_size ({self.chunk_size})"
            )
        if self.min_chunk_length <= 0:
            raise ValueError(f"min_chunk_length must be positive, got {self.min_chunk_length}")
