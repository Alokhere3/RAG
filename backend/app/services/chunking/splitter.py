"""Deterministic text splitter for document embedding preparation."""

import logging
import re
from typing import List, Optional

from app.services.chunking.schemas import Chunk, ChunkingConfig
from app.services.parsers.base import PageContent, ParseResult

logger = logging.getLogger(__name__)


class TextSplitter:
    """Splits document text into overlapping, deterministic chunks."""

    def __init__(self, config: Optional[ChunkingConfig] = None) -> None:
        self.config = config or ChunkingConfig()
        self.config.validate()

    def split_text(
        self,
        text: str,
        page_number: Optional[int] = None,
        base_offset: int = 0,
        start_index: int = 0,
    ) -> List[Chunk]:
        """Split a single string into chunks adhering to size and overlap constraints."""
        if not text or not text.strip():
            return []

        clean_text = text.strip()
        if len(clean_text) < self.config.min_chunk_length:
            return []

        # If text is already within chunk size, return single chunk
        if len(clean_text) <= self.config.chunk_size:
            return [
                Chunk(
                    index=start_index,
                    text=clean_text,
                    char_start=base_offset,
                    char_end=base_offset + len(clean_text),
                    page_number=page_number,
                    metadata={
                        "chunking_strategy": self.config.strategy,
                        "chunking_version": self.config.version,
                    },
                )
            ]

        raw_splits = self._split_recursive(clean_text, self.config.separators)
        chunks_text = self._merge_splits(raw_splits)

        chunks: List[Chunk] = []
        curr_offset = base_offset
        search_start = 0

        for i, chunk_text in enumerate(chunks_text):
            chunk_clean = chunk_text.strip()
            if len(chunk_clean) < self.config.min_chunk_length:
                continue

            # Locate position in text to compute accurate character span
            pos = clean_text.find(chunk_clean, search_start)
            if pos != -1:
                chunk_start = base_offset + pos
                chunk_end = chunk_start + len(chunk_clean)
                # Next search starts with overlap consideration
                search_start = max(pos + 1, pos + len(chunk_clean) - self.config.chunk_overlap)
            else:
                chunk_start = curr_offset
                chunk_end = curr_offset + len(chunk_clean)
                curr_offset = chunk_end

            chunks.append(
                Chunk(
                    index=start_index + len(chunks),
                    text=chunk_clean,
                    char_start=chunk_start,
                    char_end=chunk_end,
                    page_number=page_number,
                    metadata={
                        "chunking_strategy": self.config.strategy,
                        "chunking_version": self.config.version,
                    },
                )
            )

        return chunks

    def split_parse_result(self, parse_result: ParseResult) -> List[Chunk]:
        """Split a full ParseResult, preserving per-page tracking and offsets."""
        all_chunks: List[Chunk] = []
        cumulative_offset = 0

        if parse_result.pages:
            for page in parse_result.pages:
                page_chunks = self.split_text(
                    text=page.text,
                    page_number=page.page_number,
                    base_offset=cumulative_offset,
                    start_index=len(all_chunks),
                )
                all_chunks.extend(page_chunks)
                cumulative_offset += len(page.text)
        else:
            all_chunks = self.split_text(
                text=parse_result.text,
                page_number=None,
                base_offset=0,
                start_index=0,
            )

        return all_chunks

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using the hierarchy of separators."""
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators: List[str] = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)

        for s in splits:
            if not s:
                continue
            if len(s) <= self.config.chunk_size:
                final_chunks.append(s)
            elif new_separators:
                sub_chunks = self._split_recursive(s, new_separators)
                final_chunks.extend(sub_chunks)
            else:
                # Hard character split if no separators left
                final_chunks.extend(self._hard_split(s))

        return final_chunks

    def _hard_split(self, text: str) -> List[str]:
        """Split text strictly by character length when no separator matches."""
        chunks = []
        step = max(1, self.config.chunk_size - self.config.chunk_overlap)
        for i in range(0, len(text), step):
            chunks.append(text[i : i + self.config.chunk_size])
        return chunks

    def _merge_splits(self, splits: List[str]) -> List[str]:
        """Combine raw splits into chunks up to chunk_size with overlap."""
        merged: List[str] = []
        current_chunk: List[str] = []
        current_len = 0

        for piece in splits:
            piece_len = len(piece)

            if current_len + piece_len + 1 > self.config.chunk_size and current_chunk:
                merged_text = " ".join(current_chunk)
                merged.append(merged_text)

                # Keep overlap tail for the next chunk
                overlap_len = 0
                new_current: List[str] = []
                for p in reversed(current_chunk):
                    if overlap_len + len(p) <= self.config.chunk_overlap:
                        new_current.insert(0, p)
                        overlap_len += len(p)
                    else:
                        break

                current_chunk = new_current
                current_len = sum(len(p) for p in current_chunk)

            current_chunk.append(piece)
            current_len += piece_len

        if current_chunk:
            merged.append(" ".join(current_chunk))

        return merged
