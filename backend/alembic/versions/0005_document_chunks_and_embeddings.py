"""Create document_chunks and vector_index_metadata tables for Phase 5.

Revision ID: 0005_chunks_and_embeddings
Revises: 0004_ingestion_jobs
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from app.models.chunk import VectorType

# revision identifiers, used by Alembic.
revision: str = "0005_chunks_and_embeddings"
down_revision: Union[str, None] = "0004_ingestion_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create document_chunks and vector_index_metadata tables."""
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        # Enable pgvector extension on PostgreSQL
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), server_default="0", nullable=False),
        sa.Column("char_end", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", VectorType(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_chunks_embedding_model"), "document_chunks", ["embedding_model"], unique=False)
    op.create_index("ix_chunks_doc_idx", "document_chunks", ["document_id", "chunk_index"], unique=False)

    op.create_table(
        "vector_index_metadata",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("chunking_version", sa.String(length=50), nullable=False),
        sa.Column("index_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vector_index_metadata_is_active"), "vector_index_metadata", ["is_active"], unique=False)


def downgrade() -> None:
    """Drop document_chunks and vector_index_metadata tables."""
    op.drop_index(op.f("ix_vector_index_metadata_is_active"), table_name="vector_index_metadata")
    op.drop_table("vector_index_metadata")

    op.drop_index("ix_chunks_doc_idx", table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_embedding_model"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
