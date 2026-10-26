"""Data models for document chunks, embeddings, and vector index metadata."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.db.base import Base

JSON = JSONB().with_variant(sa.JSON(), "sqlite")
Uuid = sa.Uuid


class VectorType(TypeDecorator):
    """Vector type using pgvector on PostgreSQL and JSON arrays on SQLite."""

    impl = sa.JSON
    cache_ok = True
    comparator_factory = Vector.comparator_factory

    def __init__(self, dimensions: Optional[int] = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimensions) if self.dimensions else Vector())
        return dialect.type_descriptor(sa.JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, "tolist"):
            return value.tolist()
        return value


class DocumentChunk(Base):
    """A persistent chunk of a source document along with its embedding vector."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    char_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    token_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    page_number: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    char_start: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    char_end: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    embedding: Mapped[Optional[List[float]]] = mapped_column(
        VectorType(),
        nullable=True,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
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
    )

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        sa.Index("ix_chunks_doc_idx", "document_id", "chunk_index"),
    )


class VectorIndexMetadata(Base):
    """Tracks active embedding model, vector dimensions, and chunking schema version."""

    __tablename__ = "vector_index_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    dimensions: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    chunking_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    index_version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
