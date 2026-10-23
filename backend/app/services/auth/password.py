"""Password hashing, verification, and policy enforcement service.

Uses Argon2id (RFC 9106 recommended profile) as the primary hashing algorithm,
with transparent bcrypt verification support for fallback/legacy hashes.
Passwords are never logged or exposed in responses.
"""

import logging
from typing import Optional

try:
    import argon2
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
    _ARGON2_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ARGON2_AVAILABLE = False

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BCRYPT_AVAILABLE = False

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PasswordPolicyError(ValueError):
    """Raised when a password does not satisfy security policy criteria."""

    pass


# RFC 9106 recommended parameters: memory 64MB (65536 KiB), time 3 iterations, 4 parallel threads
_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
) if _ARGON2_AVAILABLE else None


def validate_password_policy(
    password: str,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> None:
    """Validate password against security policy rules.

    Args:
        password: The plaintext candidate password.
        min_length: Optional minimum length override (defaults to settings.password_min_length).
        max_length: Optional maximum length override (defaults to settings.password_max_length).

    Raises:
        PasswordPolicyError: If password is empty, too short, or too long.
    """
    if not isinstance(password, str) or not password:
        raise PasswordPolicyError("Password must be a non-empty string.")

    settings = get_settings()
    min_len = min_length if min_length is not None else settings.password_min_length
    max_len = max_length if max_length is not None else settings.password_max_length

    if len(password) < min_len:
        raise PasswordPolicyError(
            f"Password is too short. It must be at least {min_len} characters long."
        )

    if len(password) > max_len:
        raise PasswordPolicyError(
            f"Password exceeds maximum allowed length of {max_len} characters."
        )


def hash_password(password: str) -> str:
    """Hash a password using Argon2id with automatic policy validation.

    Args:
        password: The plaintext password to hash.

    Returns:
        The serialized Argon2id or bcrypt hash string.

    Raises:
        PasswordPolicyError: If the password violates length or content policy.
    """
    validate_password_policy(password)

    if _ARGON2_AVAILABLE and _HASHER is not None:
        return _HASHER.hash(password)

    if _BCRYPT_AVAILABLE:
        # Fallback to bcrypt if Argon2 is not available
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    raise RuntimeError("No cryptographic password hashing provider (Argon2 / bcrypt) is available.")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored hash (Argon2id or bcrypt).

    Args:
        password: The candidate plaintext password.
        password_hash: The stored serialized hash string.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    if not password or not password_hash or not isinstance(password, str) or not isinstance(password_hash, str):
        return False

    # 1. Argon2id verification
    if password_hash.startswith("$argon2"):
        if not _ARGON2_AVAILABLE or _HASHER is None:
            logger.error("Argon2 hash encountered but argon2-cffi is not available.")
            return False
        try:
            return _HASHER.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    # 2. Bcrypt verification fallback
    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        if not _BCRYPT_AVAILABLE:
            logger.error("Bcrypt hash encountered but bcrypt is not available.")
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False

    logger.warning("Unrecognized password hash scheme.")
    return False


def needs_rehash(password_hash: str) -> bool:
    """Check if the password hash should be upgraded to current algorithm parameters.

    Args:
        password_hash: The stored password hash string.

    Returns:
        True if the hash is legacy (e.g. bcrypt) or outdated Argon2 parameters, False otherwise.
    """
    if not password_hash or not isinstance(password_hash, str):
        return False

    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return True

    if password_hash.startswith("$argon2") and _ARGON2_AVAILABLE and _HASHER is not None:
        try:
            return _HASHER.check_needs_rehash(password_hash)
        except Exception:
            return True

    return False
