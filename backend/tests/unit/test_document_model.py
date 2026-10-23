"""Unit tests for Document ORM model (Chunk 3.1)."""

import uuid
import pytest
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole, UserStatus


def test_document_model_defaults_and_initialization():
    """Verify document model auto-generates UUID, sets default status, and attributes."""
    user_id = uuid.uuid4()
    doc = Document(
        filename="report.pdf",
        storage_key=f"documents/{uuid.uuid4()}_report.pdf",
        content_type="application/pdf",
        file_size=1024,
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        uploader_id=user_id,
    )

    assert isinstance(doc.id, uuid.UUID)
    assert doc.filename == "report.pdf"
    assert doc.content_type == "application/pdf"
    assert doc.file_size == 1024
    assert doc.status == DocumentStatus.UPLOADED
    assert doc.uploader_id == user_id
    assert doc.metadata_json == {}
    assert "report.pdf" in repr(doc)


def test_document_status_enum_values():
    """Verify document status enum covers expected lifecycle states."""
    expected_values = {"uploaded", "processing", "ready", "failed", "deleted"}
    actual_values = {e.value for e in DocumentStatus}
    assert expected_values == actual_values
