"""Durable Ingestion Service managing parsing jobs, worker leases, retries, and artifacts.

Conforms to Phase 4 requirements:
- Upload + durable file -> durable job record -> worker -> parser -> normalized text artifact/status
- State machine: queued -> processing -> succeeded / failed / cancelled
- Worker leases and crash recovery (I007)
- Bounded retries with permanent error short-circuit (I008, I009)
- Idempotent job creation and dispatch (I010)
- Concurrency-safe job claiming (I011)
- Safe error codes and sanitized logs without document text (I017)
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    CorruptFileError,
    NotFoundError,
    OcrRequiredError,
    ParserError,
    ParserTimeoutError,
    UnsupportedFormatError,
)
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, JobStatus
from app.services.parsers.registry import default_parser_registry
from app.services.storage.local import storage_service

logger = logging.getLogger(__name__)


class IngestionService:
    """Service orchestrating document ingestion jobs, execution, and artifact storage."""

    def __init__(self) -> None:
        self.parser_registry = default_parser_registry
        self.storage = storage_service

    async def create_or_get_job(
        self,
        db: AsyncSession,
        document_id: uuid.UUID,
        force_reprocess: bool = False,
    ) -> IngestionJob:
        """Create a new ingestion job or return existing active job (idempotent)."""
        # Verify document exists
        doc_stmt = select(Document).where(Document.id == document_id)
        doc_res = await db.execute(doc_stmt)
        document = doc_res.scalar_one_or_none()

        if not document:
            raise NotFoundError(f"Document '{document_id}' not found.")

        if document.status == DocumentStatus.DELETED:
            raise NotFoundError(f"Document '{document_id}' has been deleted.")

        # Check for active existing job (queued or processing)
        active_stmt = (
            select(IngestionJob)
            .where(
                IngestionJob.document_id == document_id,
                IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
            )
            .order_by(IngestionJob.created_at.desc())
        )
        active_res = await db.execute(active_stmt)
        existing_active = active_res.scalars().first()

        if existing_active and not force_reprocess:
            logger.info("JOB_REUSED document_id=%s job_id=%s status=%s", document_id, existing_active.id, existing_active.status)
            return existing_active

        # If document already ready and not forcing, return latest succeeded job
        if document.status == DocumentStatus.READY and not force_reprocess:
            succeeded_stmt = (
                select(IngestionJob)
                .where(
                    IngestionJob.document_id == document_id,
                    IngestionJob.status == JobStatus.SUCCEEDED,
                )
                .order_by(IngestionJob.created_at.desc())
            )
            succeeded_res = await db.execute(succeeded_stmt)
            latest_succeeded = succeeded_res.scalars().first()
            if latest_succeeded:
                return latest_succeeded

        # Create new queued job
        new_job = IngestionJob(
            document_id=document_id,
            status=JobStatus.QUEUED,
        )
        db.add(new_job)
        await db.commit()
        await db.refresh(new_job)

        logger.info("JOB_CREATED document_id=%s job_id=%s", document_id, new_job.id)
        return new_job

    async def claim_next_job(
        self,
        db: AsyncSession,
        worker_id: str,
        lease_seconds: Optional[int] = None,
    ) -> Optional[IngestionJob]:
        """Atomically claim a queued or expired processing job for the worker."""
        settings = get_settings()
        lease_duration = lease_seconds or settings.ingestion_lease_seconds
        now = datetime.now(timezone.utc)
        lease_expires_at = now + timedelta(seconds=lease_duration)

        # 1. Recover stale crashed jobs first
        await self.recover_stale_jobs(db)

        # 2. Query candidate job IDs ordered by creation time
        candidates_stmt = (
            select(IngestionJob.id)
            .where(
                IngestionJob.status == JobStatus.QUEUED,
                IngestionJob.attempt_count < IngestionJob.max_attempts,
            )
            .order_by(IngestionJob.created_at.asc())
            .limit(10)
        )
        res = await db.execute(candidates_stmt)
        candidate_ids = res.scalars().all()

        for cand_id in candidate_ids:
            # Atomic conditional claim: rowcount == 1 only if still QUEUED at update time
            update_stmt = (
                update(IngestionJob)
                .where(
                    IngestionJob.id == cand_id,
                    IngestionJob.status == JobStatus.QUEUED,
                )
                .values(
                    status=JobStatus.PROCESSING,
                    worker_id=worker_id,
                    lease_timeout_at=lease_expires_at,
                    attempt_count=IngestionJob.attempt_count + 1,
                    started_at=func.coalesce(IngestionJob.started_at, now),
                )
            )
            result = await db.execute(update_stmt)
            if result.rowcount == 1:
                await db.commit()
                claimed_job = await db.get(IngestionJob, cand_id)
                if claimed_job:
                    logger.info(
                        "JOB_CLAIMED job_id=%s document_id=%s worker_id=%s attempt=%d/%d",
                        claimed_job.id,
                        claimed_job.document_id,
                        worker_id,
                        claimed_job.attempt_count,
                        claimed_job.max_attempts,
                    )
                    return claimed_job

        return None

    async def process_job(
        self,
        db: AsyncSession,
        job_id: uuid.UUID,
        worker_id: str,
    ) -> IngestionJob:
        """Execute text extraction for a claimed job with resource bounds and safety."""
        settings = get_settings()

        job_stmt = select(IngestionJob).where(IngestionJob.id == job_id)
        job_res = await db.execute(job_stmt)
        job = job_res.scalar_one_or_none()

        if not job:
            raise NotFoundError(f"IngestionJob '{job_id}' not found.")

        # Load associated document
        doc_stmt = select(Document).where(Document.id == job.document_id)
        doc_res = await db.execute(doc_stmt)
        document = doc_res.scalar_one_or_none()

        # Handle document deleted mid-processing (I015)
        if not document or document.status == DocumentStatus.DELETED:
            job.status = JobStatus.CANCELLED
            job.error_code = "DOCUMENT_DELETED"
            job.error_message = "Document was deleted during processing."
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("JOB_ABORTED_DOCUMENT_DELETED job_id=%s", job_id)
            return job

        now = datetime.now(timezone.utc)

        try:
            # 1. Read stored document bytes
            file_bytes = await self.storage.read_bytes(document.storage_key)

            # 2. Resolve parser
            parser = self.parser_registry.get_parser(document.content_type, document.filename)

            # 3. Parse with bounded timeout
            async def _run_parser():
                return await asyncio.to_thread(parser.parse, file_bytes, document.filename)

            parse_result = await asyncio.wait_for(
                _run_parser(),
                timeout=float(settings.parser_timeout_seconds),
            )

            # 4. Save extracted text artifact durably via storage service
            artifact_key = f"artifacts/{job.id}_extracted.json"
            artifact_data = parse_result.model_dump_json(indent=2).encode("utf-8")
            await self.storage.save_bytes(artifact_key, artifact_data)

            # 5. Generate chunks and embeddings in vector store (Phase 5)
            from app.services.indexing_service import indexing_service
            await indexing_service.index_document(
                session=db,
                document_id=document.id,
                text=parse_result.text,
                pages=parse_result.pages,
            )

            # 6. Success state transition
            job.status = JobStatus.SUCCEEDED
            job.parser_name = parse_result.parser_name
            job.parser_version = parse_result.parser_version
            job.page_count = parse_result.page_count
            job.char_count = parse_result.char_count
            job.extracted_text_key = artifact_key
            job.error_code = None
            job.error_message = None
            job.completed_at = datetime.now(timezone.utc)

            document.status = DocumentStatus.READY

            logger.info(
                "INGESTION_SUCCEEDED job_id=%s document_id=%s pages=%d chars=%d parser=%s",
                job.id,
                document.id,
                job.page_count,
                job.char_count,
                job.parser_name,
            )

        except asyncio.TimeoutError:
            # Parser timeout (I006)
            job.status = JobStatus.FAILED
            job.error_code = "PARSER_TIMEOUT"
            job.error_message = f"Parser exceeded maximum execution timeout of {settings.parser_timeout_seconds}s."
            job.completed_at = datetime.now(timezone.utc)
            document.status = DocumentStatus.FAILED

            logger.warning("INGESTION_TIMEOUT job_id=%s document_id=%s", job.id, document.id)

        except (CorruptFileError, OcrRequiredError, UnsupportedFormatError) as exc:
            # Permanent errors: do not retry (I009)
            job.status = JobStatus.FAILED
            job.error_code = exc.code
            job.error_message = str(exc.message)[:500]
            job.completed_at = datetime.now(timezone.utc)
            document.status = DocumentStatus.FAILED

            logger.warning(
                "INGESTION_PERMANENT_FAILURE job_id=%s document_id=%s code=%s err=%s",
                job.id,
                document.id,
                exc.code,
                exc.message,
            )

        except Exception as exc:
            # Transient error: retry with bounded attempts (I008)
            safe_msg = str(exc)[:500]
            if job.attempt_count < job.max_attempts:
                job.status = JobStatus.QUEUED
                job.error_code = "TRANSIENT_FAILURE"
                job.error_message = f"Attempt {job.attempt_count}/{job.max_attempts} failed: {safe_msg}"
                job.lease_timeout_at = None
                job.worker_id = None
                logger.warning(
                    "INGESTION_RETRY_SCHEDULED job_id=%s attempt=%d/%d err=%s",
                    job.id,
                    job.attempt_count,
                    job.max_attempts,
                    safe_msg,
                )
            else:
                job.status = JobStatus.FAILED
                job.error_code = "MAX_ATTEMPTS_EXCEEDED"
                job.error_message = f"Exceeded max attempts ({job.max_attempts}): {safe_msg}"
                job.completed_at = datetime.now(timezone.utc)
                document.status = DocumentStatus.FAILED
                logger.error(
                    "INGESTION_FAILED_MAX_RETRIES job_id=%s document_id=%s",
                    job.id,
                    document.id,
                )

        await db.commit()
        await db.refresh(job)
        return job

    async def recover_stale_jobs(self, db: AsyncSession) -> int:
        """Find crashed or timed-out worker leases and reset to QUEUED or FAILED (I007)."""
        now = datetime.now(timezone.utc)

        # Find processing jobs whose lease expired
        stale_stmt = select(IngestionJob).where(
            IngestionJob.status == JobStatus.PROCESSING,
            IngestionJob.lease_timeout_at < now,
        )
        res = await db.execute(stale_stmt)
        stale_jobs = res.scalars().all()

        recovered_count = 0
        for job in stale_jobs:
            if job.attempt_count < job.max_attempts:
                job.status = JobStatus.QUEUED
                job.worker_id = None
                job.lease_timeout_at = None
                job.error_code = "WORKER_CRASHED"
                job.error_message = "Worker lease expired; job returned to queue for retry."
                logger.warning("JOB_RECOVERED_TO_QUEUE job_id=%s attempt=%d", job.id, job.attempt_count)
            else:
                job.status = JobStatus.FAILED
                job.error_code = "WORKER_LEASE_EXPIRED"
                job.error_message = "Worker lease expired and max attempts reached."
                job.completed_at = now
                logger.error("JOB_FAILED_LEASE_EXPIRED job_id=%s", job.id)

            recovered_count += 1

        if recovered_count > 0:
            await db.commit()

        return recovered_count

    async def cancel_job(self, db: AsyncSession, job_id: uuid.UUID) -> IngestionJob:
        """Safely cancel an ingestion job."""
        stmt = select(IngestionJob).where(IngestionJob.id == job_id)
        res = await db.execute(stmt)
        job = res.scalar_one_or_none()

        if not job:
            raise NotFoundError(f"IngestionJob '{job_id}' not found.")

        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return job

        job.status = JobStatus.CANCELLED
        job.error_code = "CANCELLED_BY_USER"
        job.error_message = "Job was cancelled."
        job.completed_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(job)
        return job


ingestion_service = IngestionService()
