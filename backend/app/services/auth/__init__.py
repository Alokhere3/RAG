"""Authentication and credential services."""

from app.services.auth.password import (
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.services.auth.tokens import (
    AccessTokenPayload,
    ExpiredTokenError,
    InvalidTokenError,
    TokenError,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_access_token,
)
from app.services.auth.sessions import (
    create_refresh_session,
    revoke_all_user_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.auth.access_control import AccessControlService

__all__ = [
    # Password
    "PasswordPolicyError",
    "hash_password",
    "verify_password",
    "validate_password_policy",
    "needs_rehash",
    # Tokens
    "TokenError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "AccessTokenPayload",
    "create_access_token",
    "verify_access_token",
    "generate_refresh_token",
    "hash_refresh_token",
    # Sessions
    "create_refresh_session",
    "rotate_refresh_token",
    "revoke_refresh_token",
    "revoke_all_user_sessions",
    # Access Control
    "AccessControlService",
]
