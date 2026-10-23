"""Unit tests for IngestionJob ORM model, relationships, and lifecycle."""

from pathlib import Path
import uuid
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, JobStatus
from app.models.user import User, UserRole, UserStatus


def test_ingestion_job_model_defaults_and_initialization() -> None:
    """Verify IngestionJob model auto-generates UUID, default status, and attributes."""
    doc_id = uuid.uuid4()
    job = IngestionJob(
        document_id=doc_id,
    )

    assert isinstance(job.id, uuid.UUID)
    assert job.document_id == doc_id
    assert job.status == JobStatus.QUEUED
    assert job.attempt_count == 0
    assert job.max_attempts == 3
    assert job.error_code is None
    assert job.error_message is None
    assert job.parser_name is None
    assert job.parser_version is None
    assert job.metadata_json == {}
    assert str(doc_id) in repr(job)


def test_job_status_enum_values() -> None:
    """Verify job status enum covers required state machine lifecycle states."""
    expected_values = {"queued", "processing", "succeeded", "failed", "cancelled"}
    actual_values = {e.value for e in JobStatus}
    assert expected_values == actual_values


@pytest.fixture
async def async_db(tmp_path: Path):
    """Fixture providing an isolated AsyncSession with foreign keys enabled."""
    db_file = tmp_path / "test_ingestion_model.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_ingestion_job_persistence(async_db: AsyncSession) -> None:
    """Verify IngestionJob database persistence and retrieval."""
    user = User(
        email="job_user@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )
    async_db.add(user)
    await async_db.flush()

    doc = Document(
        filename="report.pdf",
        storage_key="test_storage_key_job",
        content_type="application/pdf",
        file_size=1024,
        checksum="abcdef123456",
        uploader_id=user.id,
    )
    async_db.add(doc)
    await async_db.flush()

    job = IngestionJob(
        document_id=doc.id,
        parser_name="pypdf",
        parser_version="5.0.0",
    )
    async_db.add(job)
    await async_db.commit()

    # Query back
    stmt = select(IngestionJob).where(IngestionJob.id == job.id)
    res = await async_db.execute(stmt)
    saved = res.scalar_one()

    assert saved.id == job.id
    assert saved.document_id == doc.id
    assert saved.status == JobStatus.QUEUED
    assert saved.parser_name == "pypdf"
    assert saved.parser_version == "5.0.0"
    assert saved.created_at is not None


@pytest.mark.asyncio
async def test_document_ingestion_jobs_cascade_delete(async_db: AsyncSession) -> None:
    """Verify deleting a Document cascades to its associated IngestionJobs."""
    user = User(
        email="cascade_user@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    )
    async_db.add(user)
    await async_db.flush()

    doc = Document(
        filename="cascade.txt",
        storage_key="cascade_storage_key",
        content_type="text/plain",
        file_size=512,
        checksum="fedcba654321",
        uploader_id=user.id,
    )
    async_db.add(doc)
    await async_db.flush()

    job1 = IngestionJob(document_id=doc.id, status=JobStatus.SUCCEEDED)
    job2 = IngestionJob(document_id=doc.id, status=JobStatus.QUEUED)
    async_db.add_all([job1, job2])
    await async_db.commit()

    # Delete the document
    await async_db.delete(doc)
    await async_db.commit()

    # Verify jobs were deleted
    stmt = select(IngestionJob).where(IngestionJob.document_id == doc.id)
    res = await async_db.execute(stmt)
    remaining_jobs = res.scalars().all()
    assert len(remaining_jobs) == 0
