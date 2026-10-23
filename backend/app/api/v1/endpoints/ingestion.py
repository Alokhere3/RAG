"""Document Ingestion API Endpoints (Phase 4).

Exposes ingestion trigger, status check, job history, and cancellation.
Strictly enforces ownership and role boundaries with anti-enumeration 404s.
"""

import asyncio
import logging
from typing import Optional
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.session import async_session_factory, get_db
from app.models.document import Document
from app.models.ingestion import IngestionJob, JobStatus
from app.models.user import User
from app.schemas.ingestion import (
    DocumentIngestionHistoryResponse,
    IngestionJobResponse,
    TriggerIngestionRequest,
)
from app.api.deps import get_current_user
from app.services.auth.access_control import AccessControlService
from app.services.ingestion_service import ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents/{document_id}/ingest", tags=["Ingestion"])


async def _run_background_ingestion(job_id: uuid.UUID) -> None:
    """Helper to process an ingestion job in a background task for immediate feedback."""
    try:
        async with async_session_factory() as session:
            worker_id = f"bg_{uuid.uuid4().hex[:6]}"
            claimed = await ingestion_service.claim_next_job(session, worker_id)
            if claimed:
                await ingestion_service.process_job(session, claimed.id, worker_id)
    except Exception as exc:
        logger.error("BACKGROUND_INGESTION_FAILED job_id=%s err=%s", job_id, exc)


@router.post(
    "",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger document ingestion",
)
async def trigger_ingestion(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: Optional[TriggerIngestionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionJobResponse:
    """Queue document for text extraction and ingestion."""
    # 1. Fetch document
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError("Document not found.")

    # 2. Authorize
    AccessControlService.authorize_document_access(current_user, document)

    # 3. Create or get job
    force = payload.force_reprocess if payload else False
    job = await ingestion_service.create_or_get_job(db, document_id, force_reprocess=force)

    # Schedule background processing if job is newly queued
    if job.status == JobStatus.QUEUED:
        background_tasks.add_task(_run_background_ingestion, job.id)

    return IngestionJobResponse.model_validate(job)


@router.get(
    "/status",
    response_model=DocumentIngestionHistoryResponse,
    summary="Get document ingestion status and history",
)
async def get_ingestion_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentIngestionHistoryResponse:
    """Return latest job status and historical runs for a document."""
    # 1. Fetch document
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError("Document not found.")

    # 2. Authorize (anti-enumeration)
    AccessControlService.authorize_document_access(current_user, document)

    # 3. Fetch jobs ordered by createdAt descending
    jobs_stmt = (
        select(IngestionJob)
        .where(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
    )
    jobs_res = await db.execute(jobs_stmt)
    all_jobs = jobs_res.scalars().all()

    current_job = all_jobs[0] if all_jobs else None
    history_responses = [IngestionJobResponse.model_validate(j) for j in all_jobs]

    return DocumentIngestionHistoryResponse(
        documentId=document.id,
        documentStatus=document.status.value,
        currentJob=IngestionJobResponse.model_validate(current_job) if current_job else None,
        history=history_responses,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobResponse,
    summary="Get single ingestion job details",
)
async def get_job_detail(
    document_id: uuid.UUID,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionJobResponse:
    """Return detail for a specific ingestion job."""
    # 1. Fetch document
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError("Document not found.")

    # 2. Authorize
    AccessControlService.authorize_document_access(current_user, document)

    # 3. Fetch job
    job_stmt = select(IngestionJob).where(
        IngestionJob.id == job_id,
        IngestionJob.document_id == document_id,
    )
    job_res = await db.execute(job_stmt)
    job = job_res.scalar_one_or_none()

    if not job:
        raise NotFoundError("Ingestion job not found.")

    return IngestionJobResponse.model_validate(job)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=IngestionJobResponse,
    summary="Cancel ingestion job",
)
async def cancel_job(
    document_id: uuid.UUID,
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionJobResponse:
    """Cancel an active or pending ingestion job."""
    stmt = select(Document).where(Document.id == document_id)
    res = await db.execute(stmt)
    document = res.scalar_one_or_none()

    if not document:
        raise NotFoundError("Document not found.")

    AccessControlService.authorize_document_access(current_user, document)

    job = await ingestion_service.cancel_job(db, job_id)
    return IngestionJobResponse.model_validate(job)
