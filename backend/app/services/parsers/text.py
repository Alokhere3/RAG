"""Text and Markdown document parser."""

import re
from typing import List

from app.core.config import get_settings
from app.core.errors import CorruptFileError, ParserError
from app.services.parsers.base import BaseParser, PageContent, ParseResult


class TextParser(BaseParser):
    """Parser for plaintext (.txt) and Markdown (.md) documents."""

    @property
    def name(self) -> str:
        return "text-parser"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def supported_mime_types(self) -> List[str]:
        return ["text/plain", "text/markdown"]

    def parse(self, content_bytes: bytes, filename: str) -> ParseResult:
        settings = get_settings()

        if not content_bytes:
            raise CorruptFileError(f"Cannot parse empty text document: {filename}")

        # Decode using standard encodings
        decoded_text = ""
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                decoded_text = content_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not decoded_text:
            raise CorruptFileError(f"Unable to decode text document using supported character sets: {filename}")

        # Normalize line breaks and remove null bytes
        normalized = decoded_text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = normalized.replace("\x00", "")

        # Check bounds
        if len(normalized) > settings.parser_max_chars:
            raise ParserError(
                f"Extracted text exceeds maximum character bound of {settings.parser_max_chars} characters.",
                code="PARSER_LIMIT_EXCEEDED",
            )

        # Split on form feed (\x0c) if present, otherwise single page
        raw_pages = normalized.split("\x0c") if "\x0c" in normalized else [normalized]
        pages: List[PageContent] = []

        total_text_parts = []
        for idx, page_str in enumerate(raw_pages, start=1):
            cleaned = page_str.strip()
            pages.append(
                PageContent(
                    page_number=idx,
                    text=cleaned,
                    char_count=len(cleaned),
                )
            )
            if cleaned:
                total_text_parts.append(cleaned)

        final_text = "\n\n".join(total_text_parts)

        return ParseResult(
            text=final_text,
            page_count=len(pages),
            char_count=len(final_text),
            pages=pages,
            parser_name=self.name,
            parser_version=self.version,
            metadata={"filename": filename, "format": "markdown" if filename.lower().endswith(".md") else "plain_text"},
        )
