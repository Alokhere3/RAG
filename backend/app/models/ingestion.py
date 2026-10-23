"""Ingestion job database ORM model and enumeration definitions."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Optional
import uuid

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document


class JobStatus(str, Enum):
    """Lifecycle statuses for document ingestion jobs."""

    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionJob(Base):
    """Durable ingestion job tracking document extraction status, retries, and errors."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        sa.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(
            JobStatus,
            name="job_status",
            native_enum=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=JobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )
    parser_name: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    parser_version: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    page_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    char_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    extracted_text_key: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    worker_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    lease_timeout_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="ingestion_jobs",
    )

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "status" not in kwargs:
            kwargs["status"] = JobStatus.QUEUED
        if "attempt_count" not in kwargs:
            kwargs["attempt_count"] = 0
        if "max_attempts" not in kwargs:
            kwargs["max_attempts"] = 3
        if "metadata_json" not in kwargs:
            kwargs["metadata_json"] = {}
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<IngestionJob id={self.id} document_id={self.document_id} status={self.status} attempts={self.attempt_count}>"
