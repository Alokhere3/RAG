"""Document parser registry and factory."""

from pathlib import Path
from typing import Dict, Optional

from app.core.errors import UnsupportedFormatError
from app.services.parsers.base import BaseParser
from app.services.parsers.docx import DocxParser
from app.services.parsers.pdf import PdfParser
from app.services.parsers.text import TextParser


class ParserRegistry:
    """Registry managing available document parser implementations."""

    def __init__(self) -> None:
        self._parsers_by_mime: Dict[str, BaseParser] = {}
        self._parsers_by_ext: Dict[str, BaseParser] = {}

        # Register standard parsers
        text_parser = TextParser()
        pdf_parser = PdfParser()
        docx_parser = DocxParser()

        self.register_parser(text_parser, extensions=[".txt", ".md"])
        self.register_parser(pdf_parser, extensions=[".pdf"])
        self.register_parser(docx_parser, extensions=[".docx"])

    def register_parser(self, parser: BaseParser, extensions: list[str]) -> None:
        """Register a parser instance for specific MIME types and file extensions."""
        for mime in parser.supported_mime_types:
            self._parsers_by_mime[mime.lower()] = parser

        for ext in extensions:
            self._parsers_by_ext[ext.lower()] = parser

    def get_parser(self, content_type: Optional[str], filename: str) -> BaseParser:
        """Find the appropriate parser for a given MIME type or file extension.

        Raises:
            UnsupportedFormatError: If no registered parser supports the file.
        """
        if content_type:
            clean_mime = content_type.lower().split(";")[0].strip()
            if clean_mime in self._parsers_by_mime:
                return self._parsers_by_mime[clean_mime]

        ext = Path(filename).suffix.lower()
        if ext in self._parsers_by_ext:
            return self._parsers_by_ext[ext]

        raise UnsupportedFormatError(
            f"No registered document parser found for file '{filename}' with content-type '{content_type}'."
        )


# Global default registry instance
default_parser_registry = ParserRegistry()
