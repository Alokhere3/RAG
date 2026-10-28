"""Local durable storage service for uploaded documents.

Enforces:
- Extension allowlist (.pdf, .txt, .md, .markdown, .docx)
- Magic byte validation and MIME spoofing detection
- Bounded file sizes and streaming writes
- Safe key generation and path traversal prevention
- Atomic temporary writes and rollback/cleanup on failure
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path
import re
from typing import AsyncIterable, Optional, Set, Tuple
import uuid

from app.core.config import get_settings
from app.core.errors import FileValidationError, PayloadTooLargeError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: Set[str] = {".pdf", ".txt", ".md", ".markdown", ".docx"}

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize original filename to prevent path traversal and strip illegal characters."""
    base_name = Path(filename).name.strip()
    # Strip any directory separators that might have slipped through
    base_name = re.sub(r"[\\/]", "_", base_name)
    # Sanitize characters to alphanumeric, dots, underscores, dashes
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", base_name)
    # Ensure non-empty
    if not sanitized or sanitized.startswith("."):
        sanitized = f"upload_{uuid.uuid4().hex[:8]}{sanitized}"
    return sanitized[:255]


def validate_file_signature(extension: str, initial_chunk: bytes) -> str:
    """Validate initial byte signatures to detect MIME spoofing and illegal binaries."""
    ext = extension.lower()

    if ext == ".pdf":
        if not initial_chunk.startswith(b"%PDF-"):
            raise FileValidationError(
                message="File content does not match PDF format (MIME spoofing detected).",
                code="MIME_SPOOFING",
            )
        return MIME_TYPES[".pdf"]

    if ext == ".docx":
        # DOCX files are zip archives starting with standard zip magic bytes
        if not initial_chunk.startswith(b"PK\x03\x04"):
            raise FileValidationError(
                message="File content does not match DOCX format (MIME spoofing detected).",
                code="MIME_SPOOFING",
            )
        return MIME_TYPES[".docx"]

    if ext in {".txt", ".md", ".markdown"}:
        # Plain text must not contain binary null bytes
        if b"\x00" in initial_chunk:
            raise FileValidationError(
                message="Binary content detected in text document.",
                code="BINARY_IN_TEXT",
            )
        try:
            initial_chunk.decode("utf-8")
        except UnicodeDecodeError:
            try:
                initial_chunk.decode("latin-1")
            except Exception as exc:
                raise FileValidationError(
                    message="Text document cannot be decoded.",
                    code="INVALID_ENCODING",
                ) from exc
        return MIME_TYPES[ext]

    raise FileValidationError(
        message=f"Unsupported file extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        code="UNSUPPORTED_FILE_TYPE",
    )


class LocalStorageService:
    """Service managing durable document storage on the local volume."""

    def __init__(self, base_dir: Optional[str] = None):
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.storage_dir).resolve()
        self.tmp_dir = self.base_dir / "tmp"
        self.documents_dir = self.base_dir / "documents"

    def _ensure_directories(self) -> None:
        """Ensure storage directory hierarchy exists."""
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.documents_dir.mkdir(parents=True, exist_ok=True)

    def resolve_storage_path(self, storage_key: str) -> Path:
        """Resolve storage key to an absolute filesystem Path, verifying it does not escape base_dir."""
        target_path = (self.base_dir / storage_key).resolve()
        if not target_path.is_relative_to(self.base_dir):
            raise FileValidationError(
                message="Invalid storage key (path traversal detected).",
                code="PATH_TRAVERSAL",
            )
        return target_path

    async def save_stream(
        self,
        stream: AsyncIterable[bytes],
        filename: str,
    ) -> Tuple[str, str, int, str]:
        """Save a streamed upload atomically with checksumming, size bounds, and validation.

        Returns:
            Tuple of (storage_key, sha256_checksum, total_bytes, detected_mime_type)
        """
        settings = get_settings()
        max_size = settings.max_upload_size_bytes

        clean_filename = sanitize_filename(filename)
        ext = Path(clean_filename).suffix.lower()

        if ext not in ALLOWED_EXTENSIONS:
            raise FileValidationError(
                message=f"File extension '{ext}' is not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
                code="UNSUPPORTED_FILE_TYPE",
            )

        self._ensure_directories()

        tmp_filename = f"tmp_{uuid.uuid4().hex}.tmp"
        tmp_path = self.tmp_dir / tmp_filename

        hasher = hashlib.sha256()
        total_size = 0
        initial_chunk_captured = False
        detected_mime = ""

        try:
            with open(tmp_path, "wb") as f:
                async for chunk in stream:
                    if not chunk:
                        continue

                    total_size += len(chunk)
                    if total_size > max_size:
                        raise PayloadTooLargeError(
                            message=f"File exceeds maximum permitted upload size of {max_size} bytes.",
                            code="PAYLOAD_TOO_LARGE",
                        )

                    if not initial_chunk_captured:
                        detected_mime = validate_file_signature(ext, chunk[:4096])
                        initial_chunk_captured = True

                    hasher.update(chunk)
                    f.write(chunk)

            if total_size == 0 or not initial_chunk_captured:
                raise FileValidationError(
                    message="Uploaded file is empty (0 bytes).",
                    code="EMPTY_FILE",
                )

            checksum = hasher.hexdigest()
            doc_id = uuid.uuid4()
            storage_key = f"documents/{doc_id}_{clean_filename}"
            final_path = self.resolve_storage_path(storage_key)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomic replace/rename from tmp to destination
            os.replace(tmp_path, final_path)

            logger.info(
                "DOCUMENT_SAVED key=%s size=%d checksum=%s",
                storage_key,
                total_size,
                checksum,
            )
            return storage_key, checksum, total_size, detected_mime

        except Exception:
            # Clean up partial temporary file on any error
            if tmp_path.exists():
                try:
                    os.remove(tmp_path)
                except Exception as cleanup_err:
                    logger.warning("FAILED_TO_CLEAN_TMP file=%s err=%s", tmp_path, cleanup_err)
            raise

    async def read_bytes(self, storage_key: str) -> bytes:
        """Safely read raw file bytes from storage by key."""
        path = self.resolve_storage_path(storage_key)
        if not path.exists() or not path.is_file():
            from app.core.errors import NotFoundError
            raise NotFoundError(f"Storage object not found.")

        # Read binary data
        with open(path, "rb") as f:
            return f.read()

    async def save_bytes(self, storage_key: str, data: bytes) -> str:
        """Atomically persist raw bytes to storage at the given key."""
        final_path = self.resolve_storage_path(storage_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self.tmp_dir / f"tmp_{uuid.uuid4().hex}"
        tmp_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(tmp_path, "wb") as f:
                f.write(data)
            os.replace(tmp_path, final_path)
            return storage_key
        except Exception:
            if tmp_path.exists():
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise

    async def delete_file(self, storage_key: str) -> bool:
        """Safely delete a stored document from disk."""
        try:
            path = self.resolve_storage_path(storage_key)
            if path.exists() and path.is_file():
                os.remove(path)
                logger.info("DOCUMENT_DELETED_FROM_DISK key=%s", storage_key)
                return True
            return False
        except Exception as exc:
            logger.warning("DOCUMENT_DISK_DELETION_FAILED key=%s err=%s", storage_key, exc)
            return False


storage_service = LocalStorageService()
