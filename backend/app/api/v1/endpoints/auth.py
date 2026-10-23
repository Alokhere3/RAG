"""Authentication REST API endpoints.

Exposes:
- POST /api/v1/auth/login: Authenticate credentials, issue access token and secure refresh cookie.
- POST /api/v1/auth/refresh: Rotate refresh token session, issue new access token.
- POST /api/v1/auth/logout: Revoke refresh session, clear cookie.
- GET  /api/v1/auth/me: Retrieve authenticated user profile.
"""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.db.session import get_db
from app.models.user import User, UserStatus, normalize_email
from app.schemas.auth import LoginRequest, LoginResponse, MessageResponse, UserResponse
from app.services.auth.password import verify_password
from app.services.auth.rate_limit import enforce_login_rate_limit
from app.services.auth.sessions import (
    create_refresh_session,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.auth.tokens import (
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    generate_refresh_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_auth_cookie(response: Response, raw_token: str) -> None:
    """Helper attaching a hardened HttpOnly refresh token cookie to the response."""
    settings = get_settings()
    is_secure = settings.auth_cookie_secure or settings.is_production
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=raw_token,
        httponly=True,
        secure=is_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )


def _clear_auth_cookie(response: Response) -> None:
    """Helper expiring and clearing the refresh token cookie with matching security attributes."""
    settings = get_settings()
    is_secure = settings.auth_cookie_secure or settings.is_production
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/api/v1/auth",
        httponly=True,
        secure=is_secure,
        samesite=settings.auth_cookie_samesite,
    )


def verify_csrf_origin(request: Request) -> None:
    """Validate Origin/Referer against allowed origins for cookie-authenticated state-changing routes."""
    settings = get_settings()
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    target = origin
    if not target and referer:
        from urllib.parse import urlparse
        parsed = urlparse(referer)
        target = f"{parsed.scheme}://{parsed.netloc}"

    if not target:
        # If in production and refresh cookie is present, require Origin or Referer
        if settings.is_production and settings.auth_cookie_name in request.cookies:
            raise AuthorizationError(
                message="Origin header is required for cookie-authenticated requests in production.",
                code="CSRF_VALIDATION_FAILED",
            )
        return

    target = target.rstrip("/")
    allowed = {o.rstrip("/") for o in settings.parsed_cors_origins}

    if "*" not in allowed and target not in allowed:
        logger.warning("CSRF_REJECTED: Untrusted origin=%s", target)
        raise AuthorizationError(
            message="Cross-origin request rejected.",
            code="UNTRUSTED_ORIGIN",
        )


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and establish session",
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate email and password, setting an HttpOnly cookie and returning an access token."""
    clean_email = normalize_email(payload.email)
    client_ip = request.client.host if request.client else None
    await enforce_login_rate_limit(client_ip, clean_email)
    stmt = select(User).where(User.email == clean_email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    # Generic error message to prevent account enumeration
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.info("LOGIN_FAILED: Invalid credentials.")
        raise AuthenticationError(
            message="Invalid email or password.",
            code="INVALID_CREDENTIALS",
        )

    if user.status != UserStatus.ACTIVE:
        logger.warning("LOGIN_REJECTED: User status=%s for user_id=%s", user.status, user.id)
        raise AuthorizationError(
            message=f"User account is {user.status.value}.",
            code="USER_INACTIVE",
        )

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)

    # Issue credentials
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    raw_refresh = generate_refresh_token()

    user_agent = request.headers.get("user-agent")

    await create_refresh_session(
        session=session,
        user_id=user.id,
        raw_token=raw_refresh,
        user_agent=user_agent,
        ip_address=client_ip,
    )

    _set_auth_cookie(response, raw_refresh)
    logger.info("LOGIN_SUCCESS: Authenticated user_id=%s", user.id)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
    )


@router.post(
    "/refresh",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate refresh token and issue new access token",
)
async def refresh_tokens(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Rotate the refresh token session from cookie and issue a fresh access token."""
    verify_csrf_origin(request)
    settings = get_settings()
    raw_refresh = request.cookies.get(settings.auth_cookie_name)

    if not raw_refresh:
        logger.debug("REFRESH_REJECTED: Missing refresh token cookie.")
        raise AuthenticationError(
            message="Refresh token cookie is missing.",
            code="MISSING_REFRESH_TOKEN",
        )

    new_raw_refresh = generate_refresh_token()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        _old_record, new_record = await rotate_refresh_token(
            session=session,
            raw_token=raw_refresh,
            new_raw_token=new_raw_refresh,
            user_agent=user_agent,
            ip_address=client_ip,
        )
    except ExpiredTokenError as exc:
        _clear_auth_cookie(response)
        raise AuthenticationError(
            message="Refresh token has expired.",
            code="TOKEN_EXPIRED",
        ) from exc
    except InvalidTokenError as exc:
        _clear_auth_cookie(response)
        raise AuthenticationError(
            message=str(exc),
            code="INVALID_REFRESH_TOKEN",
        ) from exc

    user = await session.get(User, new_record.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        _clear_auth_cookie(response)
        raise AuthenticationError(
            message="User account is no longer active.",
            code="USER_INACTIVE",
        )

    new_access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
    )
    _set_auth_cookie(response, new_raw_refresh)
    logger.debug("REFRESH_SUCCESS: Rotated tokens for user_id=%s", user.id)

    return LoginResponse(
        user=UserResponse.model_validate(user),
        access_token=new_access_token,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke session and clear refresh cookie",
)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke active refresh token in database and clear the client cookie."""
    verify_csrf_origin(request)
    settings = get_settings()
    raw_refresh = request.cookies.get(settings.auth_cookie_name)

    if raw_refresh:
        await revoke_refresh_token(session, raw_refresh)

    _clear_auth_cookie(response)
    logger.debug("LOGOUT_COMPLETED: Session revoked and cookie cleared.")
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user profile",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the profile data of the currently authenticated user."""
    return UserResponse.model_validate(current_user)
