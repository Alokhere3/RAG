"""Base abstraction and data structures for document text parsers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PageContent(BaseModel):
    """Normalized content extracted from a specific document page."""

    page_number: int = Field(ge=1, description="1-indexed page or section sequence number")
    text: str = Field(description="Extracted and normalized text content")
    char_count: int = Field(ge=0, description="Character count for this page")


class ParseResult(BaseModel):
    """Standardized output of all document parsers."""

    text: str = Field(description="Complete concatenated and normalized text of the document")
    page_count: int = Field(ge=1, description="Total number of processed pages/sections")
    char_count: int = Field(ge=0, description="Total characters extracted")
    pages: List[PageContent] = Field(default_factory=list, description="Per-page extracted text chunks")
    parser_name: str = Field(description="Identifier of parser implementation used")
    parser_version: str = Field(description="Version of parser implementation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Safe document-level metadata extracted")


class BaseParser(ABC):
    """Abstract base class for document parsers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Parser implementation identifier."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Parser implementation version."""
        pass

    @property
    @abstractmethod
    def supported_mime_types(self) -> List[str]:
        """List of MIME content types supported by this parser."""
        pass

    @abstractmethod
    def parse(self, content_bytes: bytes, filename: str) -> ParseResult:
        """Parse raw document bytes into standardized ParseResult.

        Raises:
            CorruptFileError: If the document is malformed or unreadable.
            OcrRequiredError: If document contains scanned images and no extractable text.
            ParserError: If parsing fails due to limits or unexpected errors.
        """
        pass
