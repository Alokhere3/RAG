"""FastAPI shared dependencies for authentication and authorization."""

from typing import Optional
import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, AuthorizationError
from app.db.session import get_db
from app.models.user import User, UserRole, UserStatus
from app.services.auth.tokens import (
    ExpiredTokenError,
    InvalidTokenError,
    verify_access_token,
)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Dependency validating the Bearer access token and resolving the active User entity."""
    if not auth or not auth.credentials:
        raise AuthenticationError(
            message="Authentication required.",
            code="NOT_AUTHENTICATED",
        )

    try:
        payload = verify_access_token(auth.credentials)
    except ExpiredTokenError as exc:
        raise AuthenticationError(
            message="Access token has expired.",
            code="TOKEN_EXPIRED",
        ) from exc
    except InvalidTokenError as exc:
        raise AuthenticationError(
            message="Invalid access token.",
            code="INVALID_TOKEN",
        ) from exc

    try:
        user_uuid = uuid.UUID(payload.sub)
    except (ValueError, TypeError) as exc:
        raise AuthenticationError(
            message="Invalid subject claim in token.",
            code="INVALID_TOKEN",
        ) from exc

    user = await session.get(User, user_uuid)
    if user is None:
        raise AuthenticationError(
            message="User no longer exists.",
            code="USER_NOT_FOUND",
        )

    if user.status != UserStatus.ACTIVE:
        raise AuthorizationError(
            message=f"User account is {user.status.value}.",
            code="USER_INACTIVE",
        )

    return user


from app.services.auth.access_control import AccessControlService


def require_role(required_role: UserRole):
    """Factory creating an authorization dependency requiring a specific UserRole."""
    async def _role_checker(current_user: User = Depends(get_current_user)) -> User:
        AccessControlService.authorize_role(current_user, required_role)
        return current_user

    return _role_checker


# Convenient pre-configured role dependencies
require_admin = require_role(UserRole.ADMIN)
require_user = require_role(UserRole.USER)
