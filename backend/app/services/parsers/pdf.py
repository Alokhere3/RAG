"""PDF document parser using pypdf."""

import io
from typing import List
import pypdf
from pypdf.errors import PdfReadError

from app.core.config import get_settings
from app.core.errors import CorruptFileError, OcrRequiredError, ParserError
from app.services.parsers.base import BaseParser, PageContent, ParseResult


class PdfParser(BaseParser):
    """Parser for Adobe Portable Document Format (.pdf) files."""

    @property
    def name(self) -> str:
        return "pypdf-parser"

    @property
    def version(self) -> str:
        return pypdf.__version__

    @property
    def supported_mime_types(self) -> List[str]:
        return ["application/pdf"]

    def parse(self, content_bytes: bytes, filename: str) -> ParseResult:
        settings = get_settings()

        if not content_bytes:
            raise CorruptFileError(f"Cannot parse empty PDF document: {filename}")

        try:
            stream = io.BytesIO(content_bytes)
            reader = pypdf.PdfReader(stream)
        except (PdfReadError, Exception) as exc:
            raise CorruptFileError(f"Corrupt or unreadable PDF document ({filename}): {str(exc)}") from exc

        # Check encryption / password protection
        if reader.is_encrypted:
            try:
                # Try empty password
                decrypted = reader.decrypt("")
                if not decrypted:
                    raise CorruptFileError("Password-protected PDF files are not supported.")
            except Exception as exc:
                raise CorruptFileError(f"Password-protected PDF files are not supported: {str(exc)}") from exc

        page_count = len(reader.pages)
        if page_count == 0:
            raise CorruptFileError(f"PDF document contains zero pages: {filename}")

        if page_count > settings.parser_max_pages:
            raise ParserError(
                f"PDF exceeds maximum page limit of {settings.parser_max_pages} pages (has {page_count}).",
                code="PARSER_PAGE_LIMIT_EXCEEDED",
            )

        pages: List[PageContent] = []
        full_text_chunks: List[str] = []
        total_extracted_chars = 0

        for idx, page in enumerate(reader.pages, start=1):
            try:
                raw_text = page.extract_text() or ""
            except Exception as exc:
                # Page read error, continue with other pages or record error
                raw_text = ""

            # Normalize text
            normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            normalized = normalized.replace("\x00", "").strip()

            page_len = len(normalized)
            total_extracted_chars += page_len
            pages.append(
                PageContent(
                    page_number=idx,
                    text=normalized,
                    char_count=page_len,
                )
            )
            if normalized:
                full_text_chunks.append(normalized)

        # Detect image-only PDF (no extractable text)
        if total_extracted_chars < 15:
            raise OcrRequiredError(
                f"PDF '{filename}' appears to be a scanned image or contains no digital text. "
                "OCR processing is required to extract text."
            )

        final_text = "\n\n".join(full_text_chunks)

        if len(final_text) > settings.parser_max_chars:
            raise ParserError(
                f"Extracted PDF text exceeds maximum character bound of {settings.parser_max_chars} characters.",
                code="PARSER_LIMIT_EXCEEDED",
            )

        safe_metadata = {
            "filename": filename,
            "format": "pdf",
            "page_count": page_count,
        }

        # Safe extraction of non-sensitive reader metadata if present
        if reader.metadata:
            for k in ("/Title", "/Author", "/Subject", "/Creator"):
                val = reader.metadata.get(k)
                if val and isinstance(val, str):
                    safe_metadata[k.lstrip("/").lower()] = val[:100]

        return ParseResult(
            text=final_text,
            page_count=page_count,
            char_count=len(final_text),
            pages=pages,
            parser_name=self.name,
            parser_version=self.version,
            metadata=safe_metadata,
        )
