"""Unit tests for LocalStorageService (Chunk 3.2)."""

from pathlib import Path
import pytest

from app.core.errors import FileValidationError, PayloadTooLargeError
from app.services.storage.local import LocalStorageService, sanitize_filename


async def async_iter(chunks):
    for c in chunks:
        yield c


@pytest.fixture
def temp_storage(tmp_path: Path):
    return LocalStorageService(base_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_save_valid_pdf_file(temp_storage: LocalStorageService):
    """Verify saving a valid PDF calculates checksum and returns safe storage key."""
    content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    key, checksum, size, mime = await temp_storage.save_stream(
        async_iter([content]), "test_document.pdf"
    )

    assert key.startswith("documents/")
    assert "test_document.pdf" in key
    assert size == len(content)
    assert mime == "application/pdf"
    assert len(checksum) == 64

    # Check file exists on disk
    file_path = temp_storage.resolve_storage_path(key)
    assert file_path.exists()
    assert file_path.read_bytes() == content


@pytest.mark.asyncio
async def test_save_valid_text_and_markdown_file(temp_storage: LocalStorageService):
    """Verify text and markdown files save cleanly."""
    txt_content = b"Hello, this is a plain text file for RAG platform."
    key, _, size, mime = await temp_storage.save_stream(
        async_iter([txt_content]), "notes.txt"
    )
    assert mime == "text/plain"
    assert size == len(txt_content)

    md_content = b"# Document Title\n\nMarkdown content."
    key_md, _, _, mime_md = await temp_storage.save_stream(
        async_iter([md_content]), "README.md"
    )
    assert mime_md == "text/markdown"


@pytest.mark.asyncio
async def test_save_valid_docx_file(temp_storage: LocalStorageService):
    """Verify DOCX with standard zip header saves correctly."""
    docx_content = b"PK\x03\x04" + b"\x00" * 30 + b"word/document.xml"
    key, _, size, mime = await temp_storage.save_stream(
        async_iter([docx_content]), "presentation.docx"
    )
    assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert size == len(docx_content)


@pytest.mark.asyncio
async def test_reject_empty_file(temp_storage: LocalStorageService):
    """Verify empty uploads are rejected."""
    with pytest.raises(FileValidationError) as exc_info:
        await temp_storage.save_stream(async_iter([]), "empty.txt")
    assert "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_reject_mime_spoofing(temp_storage: LocalStorageService):
    """Verify file named .pdf containing text or fake bytes is rejected."""
    fake_pdf = b"This is just normal text, not a valid PDF header!"
    with pytest.raises(FileValidationError) as exc_info:
        await temp_storage.save_stream(async_iter([fake_pdf]), "fake.pdf")
    assert "MIME_SPOOFING" in exc_info.value.code


@pytest.mark.asyncio
async def test_reject_binary_in_text_file(temp_storage: LocalStorageService):
    """Verify text file with embedded null byte is rejected as binary."""
    bad_txt = b"Hello \x00 World"
    with pytest.raises(FileValidationError) as exc_info:
        await temp_storage.save_stream(async_iter([bad_txt]), "corrupt.txt")
    assert "BINARY_IN_TEXT" in exc_info.value.code


@pytest.mark.asyncio
async def test_reject_unsupported_extension(temp_storage: LocalStorageService):
    """Verify unsupported file extensions like .exe, .sh, .py are rejected."""
    with pytest.raises(FileValidationError) as exc_info:
        await temp_storage.save_stream(async_iter([b"print('hack')"]), "script.py")
    assert "UNSUPPORTED_FILE_TYPE" in exc_info.value.code


@pytest.mark.asyncio
async def test_reject_oversized_file_and_cleans_tmp(temp_storage: LocalStorageService, monkeypatch):
    """Verify uploads exceeding max limit are aborted and partial tmp file is deleted."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)

    oversized_chunk = b"%PDF-" + b"A" * 150
    with pytest.raises(PayloadTooLargeError):
        await temp_storage.save_stream(async_iter([oversized_chunk]), "large.pdf")

    # Verify no leaked tmp files
    tmp_files = list(temp_storage.tmp_dir.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_sanitize_filename_prevents_path_traversal():
    """Verify path traversal characters are stripped from filename."""
    traversal = "../../../etc/passwd"
    clean = sanitize_filename(traversal)
    assert "/" not in clean
    assert ".." not in clean
    assert clean == "passwd"

    windows_traversal = "..\\..\\windows\\system32\\cmd.exe"
    clean_win = sanitize_filename(windows_traversal)
    assert "\\" not in clean_win
    assert ".." not in clean_win
    assert clean_win == "cmd.exe"


@pytest.mark.asyncio
async def test_delete_file(temp_storage: LocalStorageService):
    """Verify deleting a file removes it from disk and returns boolean."""
    content = b"%PDF-1.4\ncontent\n%%EOF"
    key, _, _, _ = await temp_storage.save_stream(async_iter([content]), "doc.pdf")
    path = temp_storage.resolve_storage_path(key)
    assert path.exists()

    deleted = await temp_storage.delete_file(key)
    assert deleted is True
    assert not path.exists()

    # Second delete returns False without error
    deleted_again = await temp_storage.delete_file(key)
    assert deleted_again is False
