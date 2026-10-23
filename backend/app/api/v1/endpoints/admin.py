"""Admin and operational REST API endpoints."""

import logging
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.document import DocumentStatus
from app.models.ingestion import JobStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.admin import (
    AdminDiagnosticsResponse,
    AdminRoleUpdateRequest,
    AdminStatusUpdateRequest,
    AdminUserCreateRequest,
    AdminUserListResponse,
    AdminUserResponse,
)
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.schemas.ingestion import IngestionJobResponse
from app.services.admin_service import admin_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])


class JobListResponse(BaseModel):
    """Paginated list of ingestion jobs."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[IngestionJobResponse]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")


def _to_document_response(doc) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        contentType=doc.content_type,
        fileSize=doc.file_size,
        checksum=doc.checksum,
        uploaderId=doc.uploader_id,
        status=doc.status.value if hasattr(doc.status, "value") else str(doc.status),
        createdAt=doc.created_at,
        updatedAt=doc.updated_at,
        metadata=doc.metadata_json or {},
    )


# -------------------------------------------------------------------------
# User Management Endpoints (O001 - O005)
# -------------------------------------------------------------------------


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all users with pagination and filters",
)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by email or name"),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    status_filter: Optional[UserStatus] = Query(None, alias="status", description="Filter by status"),
    session: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    """List registered users with administrative visibility."""
    users, total = await admin_service.list_users(
        session=session,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        status=status_filter,
    )
    return AdminUserListResponse(
        items=[AdminUserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/users",
    response_model=AdminUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def create_user(
    payload: AdminUserCreateRequest,
    current_admin: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """Create a new user account with administrative role assignment."""
    user = await admin_service.create_user(
        session=session,
        actor=current_admin,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role=payload.role,
    )
    return AdminUserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user authorization role",
)
async def update_user_role(
    user_id: uuid.UUID,
    payload: AdminRoleUpdateRequest,
    current_admin: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """Change user role with last-admin protection (O003, O005)."""
    user = await admin_service.update_user_role(
        session=session,
        actor=current_admin,
        target_user_id=user_id,
        new_role=payload.role,
    )
    return AdminUserResponse.model_validate(user)


@router.patch(
    "/users/{user_id}/status",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user status (active/suspended)",
)
async def update_user_status(
    user_id: uuid.UUID,
    payload: AdminStatusUpdateRequest,
    current_admin: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """Change user status with last-admin protection (O005)."""
    user = await admin_service.update_user_status(
        session=session,
        actor=current_admin,
        target_user_id=user_id,
        new_status=payload.status,
    )
    return AdminUserResponse.model_validate(user)


# -------------------------------------------------------------------------
# Document & Ingestion Operations (O006, O007, O008)
# -------------------------------------------------------------------------


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all documents system-wide",
)
async def list_all_documents(
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset"),
    status_filter: Optional[DocumentStatus] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """Admin view of all documents across all uploaders."""
    page = (offset // limit) + 1
    docs, total = await admin_service.list_all_documents(
        session=session,
        page=page,
        page_size=limit,
        status_filter=status_filter,
    )
    return DocumentListResponse(
        items=[_to_document_response(d) for d in docs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/ingestion/jobs",
    response_model=JobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all ingestion jobs system-wide",
)
async def list_all_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> JobListResponse:
    """Admin inspection of all document processing jobs (O006)."""
    jobs, total = await admin_service.list_all_jobs(
        session=session,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
    )
    return JobListResponse(
        items=[IngestionJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        pageSize=page_size,
    )


@router.post(
    "/ingestion/jobs/{job_id}/retry",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry a failed ingestion job",
)
async def retry_ingestion_job(
    job_id: uuid.UUID,
    current_admin: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> IngestionJobResponse:
    """Retry a failed or cancelled ingestion job (O007, O008)."""
    job = await admin_service.retry_ingestion_job(
        session=session,
        actor=current_admin,
        job_id=job_id,
    )
    return IngestionJobResponse.model_validate(job)


# -------------------------------------------------------------------------
# Diagnostics & Observability (O009)
# -------------------------------------------------------------------------


@router.get(
    "/diagnostics/config",
    response_model=AdminDiagnosticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Configuration and runtime diagnostics",
)
async def get_diagnostics() -> AdminDiagnosticsResponse:
    """Safe runtime diagnostics without secret exposure (O009)."""
    data = admin_service.get_configuration_diagnostics()
    return AdminDiagnosticsResponse(**data)
