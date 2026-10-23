"""Admin Service managing operational workflows, last-admin protection, and diagnostics.

Conforms to Phase 8 requirements:
- O001: Admin can list/manage users within policy
- O002: Normal user cannot manage users (403)
- O003: Role change is authorized and audited
- O004: Normal user cannot change roles
- O005: Last-admin deactivation follows safe policy
- O006: Admin can view safe document/job status
- O007: Retry of failed job is safe/idempotent
- O008: Retry of completed job has deterministic defined behavior
- O009: Configuration diagnostics expose no secrets
- O012: Admin action audit captures actor/action/time without sensitive payload
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import BadRequestError, NotFoundError
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, JobStatus
from app.models.user import User, UserRole, UserStatus, normalize_email
from app.services.auth.password import hash_password, validate_password_policy
from app.services.ingestion_service import ingestion_service

logger = logging.getLogger(__name__)


class AdminService:
    """Orchestrates administrative tasks, audit logging, and platform operations."""

    async def list_users(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
    ) -> Tuple[List[User], int]:
        """List system users with pagination and optional filtering."""
        offset = (page - 1) * page_size
        stmt = select(User)
        count_stmt = select(func.count(User.id))

        if role:
            stmt = stmt.where(User.role == role)
            count_stmt = count_stmt.where(User.role == role)
        if status:
            stmt = stmt.where(User.status == status)
            count_stmt = count_stmt.where(User.status == status)
        if search:
            clean_search = f"%{search.strip().lower()}%"
            filter_cond = sa.or_(
                func.lower(User.email).like(clean_search),
                func.lower(User.display_name).like(clean_search),
            )
            stmt = stmt.where(filter_cond)
            count_stmt = count_stmt.where(filter_cond)

        stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(page_size)

        total_res = await session.execute(count_stmt)
        total = total_res.scalar_one()

        res = await session.execute(stmt)
        users = res.scalars().all()
        return list(users), total

    async def create_user(
        self,
        session: AsyncSession,
        actor: User,
        email: str,
        password: str,
        display_name: Optional[str] = None,
        role: UserRole = UserRole.USER,
    ) -> User:
        """Create a new user with security validation and audit trail."""
        norm_email = normalize_email(email)
        if not norm_email:
            raise BadRequestError("Email address cannot be empty.", code="INVALID_EMAIL")

        # Validate password policy
        validate_password_policy(password)

        # Check existing email
        stmt = select(User).where(User.email == norm_email)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            raise BadRequestError(
                f"A user with email '{norm_email}' already exists.",
                code="EMAIL_EXISTS",
            )

        hashed = hash_password(password)
        new_user = User(
            email=norm_email,
            password_hash=hashed,
            display_name=display_name.strip() if display_name else None,
            role=role,
            status=UserStatus.ACTIVE,
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)

        # Audit log (no password)
        logger.info(
            "ADMIN_ACTION_AUDIT actor_id=%s action=CREATE_USER target_id=%s target_email=%s target_role=%s",
            actor.id,
            new_user.id,
            new_user.email,
            new_user.role.value,
        )
        return new_user

    async def update_user_role(
        self,
        session: AsyncSession,
        actor: User,
        target_user_id: uuid.UUID,
        new_role: UserRole,
    ) -> User:
        """Update a user's role while enforcing last-admin protection (O003, O005)."""
        stmt = select(User).where(User.id == target_user_id)
        target_user = (await session.execute(stmt)).scalar_one_or_none()
        if not target_user:
            raise NotFoundError(f"User '{target_user_id}' not found.")

        if target_user.role == new_role:
            return target_user

        # Last-admin protection
        if target_user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
            admin_count_stmt = select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.status == UserStatus.ACTIVE,
            )
            admin_count = (await session.execute(admin_count_stmt)).scalar_one()
            if admin_count <= 1:
                raise BadRequestError(
                    "Cannot demote the last remaining active administrator.",
                    code="LAST_ADMIN_PROTECTION",
                )

        target_user.role = new_role
        await session.commit()
        await session.refresh(target_user)

        logger.info(
            "ADMIN_ACTION_AUDIT actor_id=%s action=UPDATE_ROLE target_id=%s new_role=%s",
            actor.id,
            target_user.id,
            new_role.value,
        )
        return target_user

    async def update_user_status(
        self,
        session: AsyncSession,
        actor: User,
        target_user_id: uuid.UUID,
        new_status: UserStatus,
    ) -> User:
        """Update a user's active/suspended status while enforcing last-admin protection (O005)."""
        stmt = select(User).where(User.id == target_user_id)
        target_user = (await session.execute(stmt)).scalar_one_or_none()
        if not target_user:
            raise NotFoundError(f"User '{target_user_id}' not found.")

        if target_user.status == new_status:
            return target_user

        # Last-admin protection
        if target_user.role == UserRole.ADMIN and new_status != UserStatus.ACTIVE:
            admin_count_stmt = select(func.count(User.id)).where(
                User.role == UserRole.ADMIN,
                User.status == UserStatus.ACTIVE,
            )
            admin_count = (await session.execute(admin_count_stmt)).scalar_one()
            if admin_count <= 1:
                raise BadRequestError(
                    "Cannot deactivate the last remaining active administrator.",
                    code="LAST_ADMIN_PROTECTION",
                )

        target_user.status = new_status
        await session.commit()
        await session.refresh(target_user)

        logger.info(
            "ADMIN_ACTION_AUDIT actor_id=%s action=UPDATE_STATUS target_id=%s new_status=%s",
            actor.id,
            target_user.id,
            new_status.value,
        )
        return target_user

    async def list_all_documents(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 50,
        status_filter: Optional[DocumentStatus] = None,
    ) -> Tuple[List[Document], int]:
        """List documents across all users for operational visibility (O006)."""
        offset = (page - 1) * page_size
        stmt = select(Document)
        count_stmt = select(func.count(Document.id))

        if status_filter:
            stmt = stmt.where(Document.status == status_filter)
            count_stmt = count_stmt.where(Document.status == status_filter)

        stmt = stmt.order_by(Document.created_at.desc()).offset(offset).limit(page_size)

        total = (await session.execute(count_stmt)).scalar_one()
        docs = (await session.execute(stmt)).scalars().all()
        return list(docs), total

    async def list_all_jobs(
        self,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 50,
        status_filter: Optional[JobStatus] = None,
    ) -> Tuple[List[IngestionJob], int]:
        """List ingestion jobs system-wide (O006)."""
        offset = (page - 1) * page_size
        stmt = select(IngestionJob)
        count_stmt = select(func.count(IngestionJob.id))

        if status_filter:
            stmt = stmt.where(IngestionJob.status == status_filter)
            count_stmt = count_stmt.where(IngestionJob.status == status_filter)

        stmt = stmt.order_by(IngestionJob.created_at.desc()).offset(offset).limit(page_size)

        total = (await session.execute(count_stmt)).scalar_one()
        jobs = (await session.execute(stmt)).scalars().all()
        return list(jobs), total

    async def retry_ingestion_job(
        self,
        session: AsyncSession,
        actor: User,
        job_id: uuid.UUID,
    ) -> IngestionJob:
        """Retry a failed or cancelled ingestion job with idempotent validation (O007, O008)."""
        stmt = select(IngestionJob).where(IngestionJob.id == job_id)
        job = (await session.execute(stmt)).scalar_one_or_none()
        if not job:
            raise NotFoundError(f"Ingestion job '{job_id}' not found.")

        # O008: Deterministic refusal on completed job
        if job.status == JobStatus.SUCCEEDED:
            raise BadRequestError(
                "Job has already succeeded. Re-trigger ingestion with force_reprocess if re-indexing is required.",
                code="JOB_ALREADY_SUCCEEDED",
            )

        # Reset job state
        job.status = JobStatus.QUEUED
        job.attempt_count = 0
        job.error_code = None
        job.error_message = None
        job.worker_id = None
        job.lease_timeout_at = None
        job.completed_at = None

        # Also update parent document if it was failed
        doc_stmt = select(Document).where(Document.id == job.document_id)
        doc = (await session.execute(doc_stmt)).scalar_one_or_none()
        if doc and doc.status == DocumentStatus.FAILED:
            doc.status = DocumentStatus.PROCESSING

        await session.commit()
        await session.refresh(job)

        logger.info(
            "ADMIN_ACTION_AUDIT actor_id=%s action=RETRY_JOB target_id=%s document_id=%s",
            actor.id,
            job.id,
            job.document_id,
        )

        # Process job safely
        processed_job = await ingestion_service.process_job(
            db=session,
            job_id=job.id,
            worker_id=f"admin-retry-{actor.id}",
        )
        return processed_job

    def get_configuration_diagnostics(self) -> Dict[str, Any]:
        """Produce safe runtime configuration diagnostics without secret exposure (O009)."""
        settings = get_settings()

        return {
            "application": {
                "name": settings.app_name,
                "environment": getattr(settings.app_env, "value", str(settings.app_env)),
                "version": settings.app_version,
                "api_prefix": settings.api_v1_prefix,
            },
            "security": {
                "auth_cookie_secure": settings.auth_cookie_secure,
                "auth_cookie_samesite": settings.auth_cookie_samesite,
                "access_token_expire_minutes": settings.access_token_expire_minutes,
                "refresh_token_expire_days": settings.refresh_token_expire_days,
                "password_min_length": settings.password_min_length,
                "jwt_algorithm": settings.jwt_algorithm,
            },
            "embedding": {
                "provider": getattr(settings, "embedding_provider", "deterministic"),
                "model": getattr(settings, "embedding_model", "deterministic-384"),
                "dimensions": getattr(settings, "embedding_dimensions", 384),
            },
            "llm": {
                "provider": getattr(settings, "llm_provider", "deterministic"),
                "model": getattr(settings, "llm_model", "deterministic-v1"),
            },
            "storage_and_ingestion": {
                "max_file_size_bytes": getattr(settings, "max_upload_size_bytes", 52428800),
                "parser_timeout_seconds": settings.parser_timeout_seconds,
                "allowed_upload_extensions": list(getattr(settings, "allowed_upload_extensions", [".pdf", ".docx", ".txt", ".md"])),
            },
            "features": {
                "documents": getattr(settings, "enable_documents", True),
                "ingestion": getattr(settings, "enable_ingestion", True),
                "chat": getattr(settings, "enable_chat", True),
            },
        }


admin_service = AdminService()
