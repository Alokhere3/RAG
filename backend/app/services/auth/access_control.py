"""Centralized Access Control Service.

Implements the single canonical backend authorization resolver for role-based access control (RBAC).
Adheres to anti-redundancy rules, guaranteeing a single source of truth for permission decisions.
"""

import logging
from typing import Any
from app.core.errors import AuthorizationError
from app.models.user import User, UserRole, UserStatus

logger = logging.getLogger(__name__)


class AccessControlService:
    """Centralized service for evaluating authorization policies and role permissions."""

    @staticmethod
    def has_role(user: User, required_role: UserRole) -> bool:
        """Check if user has the required role.

        ADMIN role has supervisory access over standard USER permissions.
        Inactive or suspended users are rejected.
        """
        if user.status != UserStatus.ACTIVE:
            return False
        if user.role == UserRole.ADMIN:
            return True
        return user.role == required_role

    @classmethod
    def authorize_role(cls, user: User, required_role: UserRole) -> None:
        """Authorize user for a required role or raise an AuthorizationError (HTTP 403).

        Args:
            user: The authenticated User entity.
            required_role: The minimum UserRole required for the operation.

        Raises:
            AuthorizationError: If user is inactive or lacks required role.
        """
        logger.debug(
            "ACCESS_RESOLUTION_STARTED user_id=%s role=%s target_role=%s",
            user.id,
            user.role,
            required_role,
        )

        if user.status != UserStatus.ACTIVE:
            logger.warning(
                "ACCESS_RESOLUTION_FAILED user_id=%s status=%s",
                user.id,
                user.status,
            )
            raise AuthorizationError(
                message=f"User account is {user.status.value}.",
                code="USER_INACTIVE",
            )

        if not cls.has_role(user, required_role):
            logger.warning(
                "ACCESS_RESOLUTION_DENIED user_id=%s role=%s required_role=%s",
                user.id,
                user.role,
                required_role,
            )
            raise AuthorizationError(
                message=f"Access denied. Requires {required_role.value} role.",
                code="FORBIDDEN",
            )

        logger.debug("ACCESS_RESOLUTION_COMPLETED user_id=%s access=GRANTED", user.id)

    @classmethod
    def can_access_document(cls, user: User, document: Any) -> bool:
        """Check if user can view or manage document. Admin has full access; User has owner access."""
        if user.status != UserStatus.ACTIVE:
            return False
        if user.role == UserRole.ADMIN:
            return True
        return str(document.uploader_id) == str(user.id)

    @classmethod
    def authorize_document_access(cls, user: User, document: Any) -> None:
        """Authorize user for document access or raise NotFoundError (anti-enumeration 404)."""
        logger.debug(
            "DOCUMENT_ACCESS_RESOLUTION_STARTED user_id=%s doc_id=%s owner_id=%s",
            user.id,
            getattr(document, "id", None),
            getattr(document, "uploader_id", None),
        )
        if not cls.can_access_document(user, document):
            logger.warning(
                "DOCUMENT_ACCESS_DENIED user_id=%s doc_id=%s",
                user.id,
                getattr(document, "id", None),
            )
            from app.core.errors import NotFoundError
            raise NotFoundError(
                message="Document not found.",
                code="NOT_FOUND",
            )
        logger.debug("DOCUMENT_ACCESS_RESOLUTION_COMPLETED user_id=%s access=GRANTED", user.id)
