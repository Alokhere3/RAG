"""Refresh token session persistence, rotation, and revocation service."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Optional, Tuple
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.token import RefreshToken
from app.services.auth.tokens import (
    ExpiredTokenError,
    InvalidTokenError,
    hash_refresh_token,
)

logger = logging.getLogger(__name__)


async def create_refresh_session(
    session: AsyncSession,
    user_id: uuid.UUID,
    raw_token: str,
    expires_delta: Optional[timedelta] = None,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> RefreshToken:
    """Persist a new hashed refresh token session in the database.

    Args:
        session: Active SQLAlchemy AsyncSession.
        user_id: Unique UUID of the authenticated user.
        raw_token: Plaintext opaque refresh token to be hashed and stored.
        expires_delta: Optional lifetime override.
        user_agent: Client User-Agent string.
        ip_address: Client IP address string.

    Returns:
        The newly created RefreshToken ORM record.
    """
    settings = get_settings()
    token_hash = hash_refresh_token(raw_token)
    lifetime = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    expires_at = datetime.now(timezone.utc) + lifetime

    token_record = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=user_agent[:255] if user_agent else None,
        ip_address=ip_address[:45] if ip_address else None,
    )
    session.add(token_record)
    await session.flush()

    logger.debug("REFRESH_SESSION_CREATED user_id=%s token_id=%s", user_id, token_record.id)
    return token_record


async def rotate_refresh_token(
    session: AsyncSession,
    raw_token: str,
    new_raw_token: str,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Tuple[RefreshToken, RefreshToken]:
    """Rotate an active refresh token with automatic token reuse theft detection.

    If a previously revoked refresh token is presented, this indicates potential
    token theft. In accordance with security specifications, all active sessions
    for the affected user are immediately invalidated.

    Args:
        session: Active SQLAlchemy AsyncSession.
        raw_token: The incoming plaintext refresh token to be rotated.
        new_raw_token: The newly generated plaintext refresh token.
        user_agent: Optional updated client User-Agent.
        ip_address: Optional updated client IP address.

    Returns:
        A tuple of (old_token_record, new_token_record).

    Raises:
        InvalidTokenError: If the token is not found, revoked, or reuse is detected.
        ExpiredTokenError: If the token has expired.
    """
    token_hash = hash_refresh_token(raw_token)
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    result = await session.execute(stmt)
    old_token = result.scalar_one_or_none()

    if old_token is None:
        logger.warning("REFRESH_ROTATION_FAILED: Token not found in database.")
        raise InvalidTokenError("Refresh token not found.")

    # Security: Token Reuse Theft Detection
    if old_token.is_revoked:
        logger.critical(
            "SECURITY_ALERT: Revoked refresh token reuse detected for user_id=%s token_id=%s! "
            "Invalidating all sessions for this user.",
            old_token.user_id,
            old_token.id,
        )
        await revoke_all_user_sessions(session, old_token.user_id)
        await session.commit()
        raise InvalidTokenError("Revoked refresh token reuse detected. All active sessions invalidated.")

    # Expiration check
    if old_token.is_expired:
        logger.info("REFRESH_ROTATION_FAILED: Expired token presented for user_id=%s", old_token.user_id)
        raise ExpiredTokenError("Refresh token has expired.")

    # Revoke old token and link to replacement
    now = datetime.now(timezone.utc)
    old_token.revoked_at = now
    old_token.last_used_at = now

    # Issue and persist new token
    settings = get_settings()
    new_token_hash = hash_refresh_token(new_raw_token)
    new_expires_at = now + timedelta(days=settings.refresh_token_expire_days)

    new_token = RefreshToken(
        user_id=old_token.user_id,
        token_hash=new_token_hash,
        expires_at=new_expires_at,
        user_agent=user_agent[:255] if user_agent else old_token.user_agent,
        ip_address=ip_address[:45] if ip_address else old_token.ip_address,
    )
    session.add(new_token)
    await session.flush()

    old_token.replaced_by_token_id = new_token.id
    await session.commit()

    logger.debug(
        "REFRESH_ROTATION_COMPLETED user_id=%s old_token_id=%s new_token_id=%s",
        old_token.user_id,
        old_token.id,
        new_token.id,
    )
    return old_token, new_token


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> bool:
    """Revoke an active refresh token session upon logout.

    Args:
        session: Active SQLAlchemy AsyncSession.
        raw_token: Plaintext refresh token to revoke.

    Returns:
        True if the token was found and transitioned to revoked, False otherwise.
    """
    token_hash = hash_refresh_token(raw_token)
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    result = await session.execute(stmt)
    token = result.scalar_one_or_none()

    if token is None or token.is_revoked:
        return False

    token.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    logger.debug("REFRESH_TOKEN_REVOKED user_id=%s token_id=%s", token.user_id, token.id)
    return True


async def revoke_all_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke all active refresh sessions for a specific user.

    Args:
        session: Active SQLAlchemy AsyncSession.
        user_id: Unique UUID of the target user.

    Returns:
        Count of sessions revoked.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    result = await session.execute(stmt)
    count = result.rowcount
    logger.info("ALL_USER_SESSIONS_REVOKED user_id=%s count=%d", user_id, count)
    return count
