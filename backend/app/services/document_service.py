"""Document business logic service.

Encapsulates:
- Document upload streaming and storage coordination
- Transactional atomicity and disk rollback on DB failure (D015, D016)
- Duplicate checksum idempotency (D009)
- Role and owner-scoped pagination and retrieval (D010, D011)
- Consistent file and database deletion (D013, D014)
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple
import uuid

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FileValidationError, NotFoundError
from app.models.document import Document, DocumentStatus
from app.models.user import User, UserRole
from app.services.auth.access_control import AccessControlService
from app.services.storage.local import storage_service

logger = logging.getLogger(__name__)


async def _stream_upload_file(file: UploadFile):
    """Async generator yielding chunks from an uploaded file."""
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        yield chunk


class DocumentService:
    """Service managing document metadata lifecycle and durable storage."""

    @staticmethod
    async def create_document(
        session: AsyncSession,
        user: User,
        upload_file: UploadFile,
    ) -> Document:
        """Stream uploaded file to durable storage, calculate checksum, and persist Document metadata.

        If a database error occurs after file storage, the orphaned file is deleted (reconciliation).
        If an identical file (same SHA-256) was already uploaded by this user, the existing active document
        is returned deterministically without storing duplicate disk artifacts.
        """
        filename = upload_file.filename or "unnamed_document"
        logger.info(
            "DOCUMENT_UPLOAD_STARTED user_id=%s filename='%s'",
            user.id,
            filename,
        )

        storage_key = None
        try:
            storage_key, checksum, total_size, detected_mime = await storage_service.save_stream(
                _stream_upload_file(upload_file),
                filename=filename,
            )

            # Check for duplicate upload by this user (deterministic idempotency: D009)
            existing_query = select(Document).where(
                Document.uploader_id == user.id,
                Document.checksum == checksum,
                Document.status != DocumentStatus.DELETED,
            )
            res = await session.execute(existing_query)
            existing_doc = res.scalar_one_or_none()

            if existing_doc:
                logger.info(
                    "DUPLICATE_DOCUMENT_DETECTED user_id=%s doc_id=%s checksum=%s. Reusing existing record.",
                    user.id,
                    existing_doc.id,
                    checksum,
                )
                # Clean up redundant duplicate disk file
                await storage_service.delete_file(storage_key)
                return existing_doc

            doc = Document(
                filename=Path(filename).name,
                storage_key=storage_key,
                content_type=detected_mime,
                file_size=total_size,
                checksum=checksum,
                uploader_id=user.id,
                status=DocumentStatus.UPLOADED,
                metadata_json={
                    "original_filename": filename,
                    "extension": Path(filename).suffix.lower(),
                },
            )

            session.add(doc)
            await session.commit()
            await session.refresh(doc)

            logger.info(
                "DOCUMENT_UPLOAD_COMPLETED doc_id=%s user_id=%s size=%d",
                doc.id,
                user.id,
                doc.file_size,
            )
            return doc

        except Exception as exc:
            # Reconcile disk state if database or downstream operation failed
            if storage_key:
                logger.warning(
                    "DOCUMENT_UPLOAD_FAILED_CLEANING_DISK key=%s err=%s",
                    storage_key,
                    exc,
                )
                await storage_service.delete_file(storage_key)
            raise

    @staticmethod
    async def list_documents(
        session: AsyncSession,
        user: User,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Document], int]:
        """List documents within the client deployment.

        - ADMIN: lists all documents across deployment
        - USER: lists only own uploaded documents
        """
        # Bounded limits
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)

        base_query = select(Document).where(Document.status != DocumentStatus.DELETED)
        count_query = select(func.count(Document.id)).where(Document.status != DocumentStatus.DELETED)

        if user.role != UserRole.ADMIN:
            base_query = base_query.where(Document.uploader_id == user.id)
            count_query = count_query.where(Document.uploader_id == user.id)

        base_query = base_query.order_by(Document.created_at.desc()).limit(safe_limit).offset(safe_offset)

        total = (await session.execute(count_query)).scalar_one() or 0
        items = list((await session.execute(base_query)).scalars().all())

        return items, total

    @staticmethod
    async def get_document(
        session: AsyncSession,
        user: User,
        document_id: uuid.UUID,
    ) -> Document:
        """Retrieve single document metadata enforcing anti-enumeration authorization."""
        query = select(Document).where(
            Document.id == document_id,
            Document.status != DocumentStatus.DELETED,
        )
        doc = (await session.execute(query)).scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document not found.")

        AccessControlService.authorize_document_access(user, doc)
        return doc

    @staticmethod
    async def delete_document(
        session: AsyncSession,
        user: User,
        document_id: uuid.UUID,
    ) -> None:
        """Delete document from disk and database consistently."""
        query = select(Document).where(
            Document.id == document_id,
            Document.status != DocumentStatus.DELETED,
        )
        doc = (await session.execute(query)).scalar_one_or_none()
        if not doc:
            raise NotFoundError("Document not found.")

        AccessControlService.authorize_document_access(user, doc)

        # Delete physical file from disk
        await storage_service.delete_file(doc.storage_key)

        # Remove from database
        await session.delete(doc)
        await session.commit()

        logger.info(
            "DOCUMENT_DELETED doc_id=%s actor_id=%s",
            document_id,
            user.id,
        )


document_service = DocumentService()
