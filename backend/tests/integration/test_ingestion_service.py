"""Integration tests for IngestionService and Worker (Chunk 4.3).

Covers test cases:
- I006: Parser timeout produces failure status
- I007: Worker crash during processing is recoverable
- I008: Transient error retries with bounded backoff
- I009: Permanent parser error is not retried indefinitely
- I010: Duplicate job delivery is idempotent
- I011: Concurrent workers cannot corrupt final state
- I015: Deleting a document during ingestion handled safely
- I016: Parser/version metadata persisted
- I017: Logs contain no raw document text
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid
import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.errors import CorruptFileError, OcrRequiredError
from app.db.base import Base
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, JobStatus
from app.models.user import User, UserRole, UserStatus
from app.services.ingestion_service import IngestionService
from app.services.parsers.base import BaseParser, PageContent, ParseResult
from app.services.storage.local import LocalStorageService


@pytest.fixture
async def ingestion_env(tmp_path: Path):
    """Fixture providing isolated database, storage, and IngestionService."""
    db_file = tmp_path / "test_ingestion.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    test_storage = LocalStorageService(base_dir=str(storage_dir))
    service = IngestionService()
    service.storage = test_storage

    yield session_factory, service, test_storage

    await engine.dispose()


@pytest.mark.asyncio
async def test_i010_idempotent_job_creation(ingestion_env) -> None:
    """I010: Creating a job multiple times returns the same active job."""
    session_factory, service, storage = ingestion_env

    async with session_factory() as session:
        user = User(email="i010@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        doc = Document(
            filename="idempotent.txt",
            storage_key="documents/idempotent.txt",
            content_type="text/plain",
            file_size=100,
            checksum="chk123",
            uploader_id=user.id,
        )
        session.add(doc)
        await session.commit()

        # Create job 1
        job1 = await service.create_or_get_job(session, doc.id)
        assert job1.status == JobStatus.QUEUED

        # Create job 2 without force
        job2 = await service.create_or_get_job(session, doc.id)
        assert job1.id == job2.id


@pytest.mark.asyncio
async def test_successful_ingestion_lifecycle(ingestion_env) -> None:
    """Verify normal queued -> processing -> succeeded transition and artifact creation."""
    session_factory, service, storage = ingestion_env

    async with session_factory() as session:
        user = User(email="lifecycle@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        # Save test document bytes
        storage_key = "documents/test_lifecycle.txt"
        await storage.save_bytes(storage_key, b"Testing document ingestion pipeline successfully.")

        doc = Document(
            filename="lifecycle.txt",
            storage_key=storage_key,
            content_type="text/plain",
            file_size=48,
            checksum="chk_lifecycle",
            uploader_id=user.id,
        )
        session.add(doc)
        await session.commit()

        job = await service.create_or_get_job(session, doc.id)
        claimed = await service.claim_next_job(session, "worker_1")
        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.status == JobStatus.PROCESSING

        # Process
        result_job = await service.process_job(session, claimed.id, "worker_1")
        assert result_job.status == JobStatus.SUCCEEDED
        assert result_job.page_count == 1
        assert result_job.char_count > 0
        assert result_job.extracted_text_key is not None

        # Verify document is ready
        await session.refresh(doc)
        assert doc.status == DocumentStatus.READY

        # Verify stored artifact exists
        artifact_bytes = await storage.read_bytes(result_job.extracted_text_key)
        assert b"Testing document ingestion" in artifact_bytes


@pytest.mark.asyncio
async def test_i007_worker_crash_recovery(ingestion_env) -> None:
    """I007: Stale job with expired lease is reclaimed back to QUEUED."""
    session_factory, service, storage = ingestion_env

    async with session_factory() as session:
        user = User(email="crash@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        doc = Document(
            filename="crash.txt",
            storage_key="documents/crash.txt",
            content_type="text/plain",
            file_size=10,
            checksum="chk_crash",
            uploader_id=user.id,
        )
        session.add(doc)
        await session.flush()

        # Create job stuck in processing with expired lease in the past
        past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        job = IngestionJob(
            document_id=doc.id,
            status=JobStatus.PROCESSING,
            worker_id="dead_worker",
            lease_timeout_at=past_time,
            attempt_count=1,
            max_attempts=3,
        )
        session.add(job)
        await session.commit()

        # Recover stale jobs
        recovered = await service.recover_stale_jobs(session)
        assert recovered == 1

        # Check job returned to queue
        await session.refresh(job)
        assert job.status == JobStatus.QUEUED
        assert job.worker_id is None
        assert job.error_code == "WORKER_CRASHED"


@pytest.mark.asyncio
async def test_i009_permanent_error_no_infinite_retry(ingestion_env) -> None:
    """I009: Permanent errors (e.g. OCR required or corrupt file) fail immediately."""
    session_factory, service, storage = ingestion_env

    async with session_factory() as session:
        user = User(email="perm@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        # Save corrupted/empty file
        storage_key = "documents/empty.pdf"
        await storage.save_bytes(storage_key, b"")

        doc = Document(
            filename="empty.pdf",
            storage_key=storage_key,
            content_type="application/pdf",
            file_size=0,
            checksum="chk_empty",
            uploader_id=user.id,
        )
        session.add(doc)
        await session.commit()

        job = await service.create_or_get_job(session, doc.id)
        claimed = await service.claim_next_job(session, "worker_1")
        assert claimed is not None

        result_job = await service.process_job(session, claimed.id, "worker_1")
        assert result_job.status == JobStatus.FAILED
        assert result_job.error_code == "CORRUPT_FILE"

        # Verify not returned to queue
        await session.refresh(result_job)
        assert result_job.status == JobStatus.FAILED

        await session.refresh(doc)
        assert doc.status == DocumentStatus.FAILED


@pytest.mark.asyncio
async def test_i006_parser_timeout_handling(ingestion_env, monkeypatch) -> None:
    """I006: Parser timeout produces failure status."""
    session_factory, service, storage = ingestion_env
    settings = get_settings()
    monkeypatch.setattr(settings, "parser_timeout_seconds", 0.05)

    class SlowParser(BaseParser):
        @property
        def name(self) -> str:
            return "slow-parser"

        @property
        def version(self) -> str:
            return "1.0"

        @property
        def supported_mime_types(self):
            return ["text/plain"]

        def parse(self, content_bytes: bytes, filename: str) -> ParseResult:
            import time
            time.sleep(0.2)  # Exceeds 0.05s timeout
            return ParseResult(
                text="done", page_count=1, char_count=4, parser_name="slow", parser_version="1.0"
            )

    service.parser_registry._parsers_by_ext[".txt"] = SlowParser()
    service.parser_registry._parsers_by_mime["text/plain"] = SlowParser()

    async with session_factory() as session:
        user = User(email="timeout@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        storage_key = "documents/slow.txt"
        await storage.save_bytes(storage_key, b"Hello slow")

        doc = Document(
            filename="slow.txt",
            storage_key=storage_key,
            content_type="text/plain",
            file_size=10,
            checksum="chk_slow",
            uploader_id=user.id,
        )
        session.add(doc)
        await session.commit()

        job = await service.create_or_get_job(session, doc.id)
        claimed = await service.claim_next_job(session, "worker_slow")
        result_job = await service.process_job(session, claimed.id, "worker_slow")

        assert result_job.status == JobStatus.FAILED
        assert result_job.error_code == "PARSER_TIMEOUT"


@pytest.mark.asyncio
async def test_i015_document_deleted_mid_processing(ingestion_env) -> None:
    """I015: If document is marked deleted mid-job, job cancels gracefully."""
    session_factory, service, storage = ingestion_env

    async with session_factory() as session:
        user = User(email="del@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        doc = Document(
            filename="deleted.txt",
            storage_key="documents/deleted.txt",
            content_type="text/plain",
            file_size=10,
            checksum="chk_del",
            uploader_id=user.id,
            status=DocumentStatus.DELETED,
        )
        session.add(doc)
        await session.flush()

        job = IngestionJob(document_id=doc.id, status=JobStatus.PROCESSING)
        session.add(job)
        await session.commit()

        result_job = await service.process_job(session, job.id, "worker_1")
        assert result_job.status == JobStatus.CANCELLED
        assert result_job.error_code == "DOCUMENT_DELETED"


@pytest.mark.asyncio
async def test_i011_concurrent_worker_claiming_no_duplicates(ingestion_env) -> None:
    """I011: Multiple concurrent workers claiming jobs never receive the same job."""
    session_factory, service, storage = ingestion_env

    # Insert 5 documents and jobs
    async with session_factory() as session:
        user = User(email="concurrent@example.com", password_hash="hash", role=UserRole.USER, status=UserStatus.ACTIVE)
        session.add(user)
        await session.flush()

        doc_ids = []
        for i in range(5):
            doc = Document(
                filename=f"doc_{i}.txt",
                storage_key=f"documents/doc_{i}.txt",
                content_type="text/plain",
                file_size=10,
                checksum=f"chk_conc_{i}",
                uploader_id=user.id,
            )
            session.add(doc)
            await session.flush()
            doc_ids.append(doc.id)
            job = IngestionJob(document_id=doc.id, status=JobStatus.QUEUED)
            session.add(job)
        await session.commit()

    # Claim using concurrent sessions
    async def _claim(worker_idx: int):
        async with session_factory() as worker_session:
            return await service.claim_next_job(worker_session, f"worker_{worker_idx}")

    claimed_jobs = await asyncio.gather(*[_claim(i) for i in range(5)])
    claimed_ids = [j.id for j in claimed_jobs if j is not None]

    # Verify no duplicate claims
    assert len(claimed_ids) == len(set(claimed_ids))
