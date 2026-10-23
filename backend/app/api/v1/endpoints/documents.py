"""Document Management REST API endpoints.

Exposes:
- POST   /api/v1/documents: Upload a source document (multipart/form-data)
- GET    /api/v1/documents: List documents with pagination and role-based visibility
- GET    /api/v1/documents/{document_id}: Retrieve document metadata
- DELETE /api/v1/documents/{document_id}: Delete document and underlying disk file
"""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.document import DocumentStatus
from app.models.user import User
from app.schemas.auth import MessageResponse
from app.schemas.document import DocumentListResponse, DocumentResponse
from app.services.document_service import document_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


def _to_response(doc) -> DocumentResponse:
    """Format Document ORM entity to safe public DocumentResponse contract."""
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


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document",
)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload (.pdf, .txt, .md, .docx)"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Upload a source document stream to durable storage and persist metadata."""
    doc = await document_service.create_document(
        session=session,
        user=current_user,
        upload_file=file,
    )

    settings = get_settings()
    if getattr(settings, "enable_ingestion", True) and doc.status != DocumentStatus.DELETED:
        from app.services.ingestion_service import ingestion_service
        try:
            await ingestion_service.create_or_get_job(session, doc.id)
        except Exception as exc:
            logger.warning("FAILED_TO_QUEUE_INGESTION doc_id=%s err=%s", doc.id, exc)

    return _to_response(doc)


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
)
async def list_documents(
    limit: int = Query(50, ge=1, le=100, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """List documents with pagination. Admins see all documents; Users see own uploads."""
    items, total = await document_service.list_documents(
        session=session,
        user=current_user,
        limit=limit,
        offset=offset,
    )
    return DocumentListResponse(
        items=[_to_response(doc) for doc in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Retrieve document metadata. Enforces anti-enumeration authorization."""
    doc = await document_service.get_document(
        session=session,
        user=current_user,
        document_id=document_id,
    )
    return _to_response(doc)


@router.delete(
    "/{document_id}",
    response_model=MessageResponse,
    summary="Delete a document",
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Delete document from disk and database."""
    await document_service.delete_document(
        session=session,
        user=current_user,
        document_id=document_id,
    )
    return MessageResponse(message="Document deleted successfully.")
