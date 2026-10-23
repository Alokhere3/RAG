"""Unit tests for document parsers (Chunk 4.2).

Covers test cases:
- I001: Valid text PDF extracts expected fixture text.
- I002: TXT/Markdown extraction and normalization are correct.
- I003: DOCX extraction works.
- I004: Corrupt/empty file ends in controlled failure.
- I005: Image-only/scanned PDF reports OCR-needed.
- I012: Oversized extracted content is bounded.
- I013: Malicious content is treated as untrusted text without execution.
- I016: Parser/version metadata is persisted.
"""

import io
import docx
import pypdf
import pytest

from app.core.config import get_settings
from app.core.errors import CorruptFileError, OcrRequiredError, ParserError, UnsupportedFormatError
from app.services.parsers.docx import DocxParser
from app.services.parsers.pdf import PdfParser
from app.services.parsers.registry import ParserRegistry, default_parser_registry
from app.services.parsers.text import TextParser


MINIMAL_VALID_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj
4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
5 0 obj << /Length 44 >> stream
BT
/F1 12 Tf
72 712 Td
(Hello RAG Ingestion PDF) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000060 00000 n 
0000000117 00000 n 
0000000227 00000 n 
0000000294 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
387
%%EOF
"""


def test_i001_valid_text_pdf_extraction() -> None:
    """I001: Valid text PDF extracts expected fixture text."""
    parser = PdfParser()
    result = parser.parse(MINIMAL_VALID_PDF, "sample.pdf")

    assert result.page_count == 1
    assert "Hello RAG Ingestion PDF" in result.text
    assert result.parser_name == "pypdf-parser"
    assert result.metadata["format"] == "pdf"
    assert len(result.pages) == 1
    assert result.pages[0].page_number == 1
    assert "Hello RAG Ingestion PDF" in result.pages[0].text


def test_i002_txt_markdown_extraction_and_normalization() -> None:
    """I002: TXT/Markdown extraction and normalization are correct."""
    parser = TextParser()

    # Test CRLF, null bytes, and Markdown content
    raw_content = "# System Documentation\r\n\r\nLine 1\r\n\x00Line 2 with \r\nCRLF and\x0cPage 2 content".encode("utf-8")
    result = parser.parse(raw_content, "guide.md")

    assert result.page_count == 2
    assert "# System Documentation" in result.text
    assert "\r" not in result.text
    assert "\x00" not in result.text
    assert result.pages[0].page_number == 1
    assert "Line 1" in result.pages[0].text
    assert result.pages[1].page_number == 2
    assert "Page 2 content" in result.pages[1].text
    assert result.metadata["format"] == "markdown"


def test_i003_docx_extraction() -> None:
    """I003: DOCX extraction works with paragraphs and tables."""
    # Build in-memory DOCX
    doc = docx.Document()
    doc.add_heading("Architecture Overview", level=1)
    doc.add_paragraph("This document outlines the self-hosted RAG platform.")

    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Component"
    table.cell(0, 1).text = "Description"
    table.cell(1, 0).text = "Worker"
    table.cell(1, 1).text = "Processes ingestion jobs"

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    parser = DocxParser()
    result = parser.parse(docx_bytes, "architecture.docx")

    assert result.page_count == 1
    assert "Architecture Overview" in result.text
    assert "This document outlines the self-hosted RAG platform." in result.text
    assert "Worker | Processes ingestion jobs" in result.text
    assert result.parser_name == "docx-parser"
    assert result.metadata["table_count"] == 1


def test_i004_corrupt_and_empty_file_controlled_failure() -> None:
    """I004: Corrupt/empty file ends in controlled failure."""
    text_parser = TextParser()
    with pytest.raises(CorruptFileError) as exc_empty_txt:
        text_parser.parse(b"", "empty.txt")
    assert "Cannot parse empty" in str(exc_empty_txt.value)

    pdf_parser = PdfParser()
    with pytest.raises(CorruptFileError) as exc_empty_pdf:
        pdf_parser.parse(b"", "empty.pdf")
    assert "Cannot parse empty" in str(exc_empty_pdf.value)

    with pytest.raises(CorruptFileError) as exc_corrupt_pdf:
        pdf_parser.parse(b"%PDF-1.4 completely broken garbage bytes not a real pdf", "corrupt.pdf")
    assert "Corrupt or unreadable PDF" in str(exc_corrupt_pdf.value)

    docx_parser = DocxParser()
    with pytest.raises(CorruptFileError) as exc_corrupt_docx:
        docx_parser.parse(b"PK\x03\x04corrupt_zip_bytes", "broken.docx")
    assert "Corrupt or unreadable DOCX" in str(exc_corrupt_docx.value)


def test_i005_image_only_pdf_reports_ocr_needed() -> None:
    """I005: Image-only/scanned PDF without digital text raises OcrRequiredError."""
    # Generate a PDF with a blank page (no text)
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    blank_pdf_bytes = buf.getvalue()

    parser = PdfParser()
    with pytest.raises(OcrRequiredError) as exc_info:
        parser.parse(blank_pdf_bytes, "scanned_invoice.pdf")

    assert "OCR processing is required" in str(exc_info.value)
    assert exc_info.value.code == "OCR_REQUIRED"


def test_i012_oversized_extracted_content_bounded(monkeypatch) -> None:
    """I012: Oversized extracted content is rejected."""
    # Temporarily set max characters to 50
    settings = get_settings()
    monkeypatch.setattr(settings, "parser_max_chars", 50)

    text_parser = TextParser()
    large_text = ("A" * 100).encode("utf-8")

    with pytest.raises(ParserError) as exc_info:
        text_parser.parse(large_text, "large.txt")

    assert exc_info.value.code == "PARSER_LIMIT_EXCEEDED"


def test_i013_malicious_content_treated_as_untrusted_data() -> None:
    """I013: Malicious shell commands or script tags are treated as plain text."""
    parser = TextParser()
    malicious_payload = b"<script>alert('xss')</script>\n; rm -rf / ; cat /etc/passwd"
    result = parser.parse(malicious_payload, "../../../evil.txt")

    # Extracted as untrusted text safely, not executed
    assert "<script>alert('xss')</script>" in result.text
    assert "; rm -rf / ;" in result.text
    assert result.char_count > 0


def test_i016_parser_version_metadata_persisted() -> None:
    """I016: Parser name and version are accurately persisted in result."""
    registry = ParserRegistry()

    txt_parser = registry.get_parser("text/plain", "doc.txt")
    txt_res = txt_parser.parse(b"Hello world", "doc.txt")
    assert txt_res.parser_name == "text-parser"
    assert txt_res.parser_version == "1.0.0"

    pdf_parser = registry.get_parser("application/pdf", "doc.pdf")
    assert pdf_parser.name == "pypdf-parser"
    assert len(pdf_parser.version) > 0


def test_unsupported_format_rejection() -> None:
    """Verify registry raises UnsupportedFormatError on unhandled mime/ext."""
    registry = ParserRegistry()

    with pytest.raises(UnsupportedFormatError) as exc_info:
        registry.get_parser("audio/mp3", "song.mp3")

    assert "No registered document parser found" in str(exc_info.value)
