"""Access token (JWT) and opaque refresh token generation, hashing, and validation services."""

from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
from typing import Optional, Union
import uuid

import jwt
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Ephemeral development-only secret. Production always requires JWT_SECRET.
DEV_JWT_SECRET_FALLBACK = secrets.token_urlsafe(32)


class TokenError(Exception):
    """Base exception for authentication token errors."""

    pass


class InvalidTokenError(TokenError):
    """Raised when a token signature, format, or payload is invalid."""

    pass


class ExpiredTokenError(TokenError):
    """Raised when a token has expired."""

    pass


class AccessTokenPayload(BaseModel):
    """Structured contract for validated access token payload claims."""

    sub: str = Field(description="Subject identifier (User UUID)")
    email: str = Field(description="Normalized user email address")
    role: str = Field(description="Canonical user authorization role")
    type: str = Field(default="access", description="Token type discriminator")
    iat: int = Field(description="Issued-at timestamp (seconds since Unix epoch)")
    exp: int = Field(description="Expiration timestamp (seconds since Unix epoch)")
    jti: str = Field(description="Unique JWT identifier (UUID v4)")


def get_jwt_secret() -> str:
    """Retrieve the configured JWT secret key or safe dev fallback."""
    settings = get_settings()
    configured_secret = settings.jwt_secret.get_secret_value()
    if configured_secret.strip():
        return configured_secret
    if not settings.is_production:
        logger.warning("JWT_SECRET is unset; using an ephemeral development secret")
        return DEV_JWT_SECRET_FALLBACK
    raise RuntimeError("JWT_SECRET is required in production environment.")


def create_access_token(
    user_id: Union[uuid.UUID, str],
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Issue a signed short-lived JWT access token.

    Args:
        user_id: Unique user identifier (UUID or UUID string).
        email: User email address.
        role: User role string.
        expires_delta: Optional custom lifetime duration.

    Returns:
        Encoded and signed JWT string.
    """
    settings = get_settings()
    secret = get_jwt_secret()
    algorithm = settings.jwt_algorithm

    now = datetime.now(timezone.utc)
    lifetime = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expires_at = now + lifetime

    payload = {
        "sub": str(user_id),
        "email": email,
        "role": str(role),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }

    token = jwt.encode(payload, secret, algorithm=algorithm)
    logger.debug("ACCESS_TOKEN_ISSUED user_id=%s role=%s exp=%s", user_id, role, payload["exp"])
    return token


def verify_access_token(token: str) -> AccessTokenPayload:
    """Decode and verify a signed JWT access token.

    Args:
        token: Raw JWT access token string.

    Returns:
        AccessTokenPayload containing verified claims.

    Raises:
        ExpiredTokenError: If the token has expired.
        InvalidTokenError: If the token is invalid, malformed, or has the wrong type.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("Token must be a non-empty string.")

    settings = get_settings()
    secret = get_jwt_secret()
    algorithm = settings.jwt_algorithm

    try:
        payload_data = jwt.decode(
            token,
            secret,
            algorithms=[algorithm],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ExpiredTokenError("Access token has expired.") from exc
    except (jwt.InvalidTokenError, jwt.DecodeError) as exc:
        raise InvalidTokenError("Invalid token signature or formatting.") from exc

    token_type = payload_data.get("type")
    if token_type != "access":
        raise InvalidTokenError(f"Invalid token type '{token_type}'. Expected 'access'.")

    try:
        return AccessTokenPayload(**payload_data)
    except Exception as exc:
        raise InvalidTokenError(f"Token payload contract violation: {exc}") from exc


def generate_refresh_token() -> str:
    """Generate a high-entropy cryptographically secure opaque refresh token.

    Returns:
        A 32-byte URL-safe plaintext token string.
    """
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    """Compute the SHA-256 hex digest of a plaintext refresh token.

    Args:
        raw_token: Plaintext opaque refresh token.

    Returns:
        64-character hexadecimal hash string.
    """
    if not raw_token or not isinstance(raw_token, str):
        raise ValueError("Refresh token must be a non-empty string.")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
