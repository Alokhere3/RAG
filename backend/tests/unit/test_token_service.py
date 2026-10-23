"""Unit tests for JWT access token and opaque refresh token services."""

from datetime import timedelta
import uuid
import jwt
import pytest

from app.services.auth.tokens import (
    AccessTokenPayload,
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_access_token,
    get_jwt_secret,
)
from app.core.config import get_settings


def test_create_and_verify_access_token():
    """Verify that a valid access token encodes claims and decodes cleanly."""
    user_id = uuid.uuid4()
    email = "test.user@company.local"
    role = "admin"

    token = create_access_token(user_id=user_id, email=email, role=role)
    assert isinstance(token, str)

    payload = verify_access_token(token)
    assert isinstance(payload, AccessTokenPayload)
    assert payload.sub == str(user_id)
    assert payload.email == email
    assert payload.role == role
    assert payload.type == "access"
    assert payload.exp > payload.iat
    assert payload.jti is not None


def test_access_token_expiration():
    """Verify that expired access tokens raise ExpiredTokenError."""
    user_id = uuid.uuid4()
    # Create token expired 10 seconds ago
    token = create_access_token(
        user_id=user_id,
        email="expired@company.local",
        role="user",
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(ExpiredTokenError) as exc_info:
        verify_access_token(token)
    assert "expired" in str(exc_info.value).lower()


def test_invalid_signature_rejection():
    """Verify that tokens signed with a different secret are rejected with InvalidTokenError."""
    user_id = uuid.uuid4()
    payload = {
        "sub": str(user_id),
        "email": "hacker@evil.org",
        "role": "admin",
        "type": "access",
        "iat": 1000,
        "exp": 9999999999,
        "jti": str(uuid.uuid4()),
    }
    bogus_token = jwt.encode(payload, "wrong-secret-key-that-does-not-match", algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        verify_access_token(bogus_token)


def test_wrong_token_type_rejection():
    """Verify that a token with non-'access' type (e.g. 'refresh') is rejected."""
    settings = get_settings()
    secret = get_jwt_secret()

    payload = {
        "sub": str(uuid.uuid4()),
        "email": "user@company.local",
        "role": "user",
        "type": "refresh",  # Deliberately invalid type
        "iat": 1000,
        "exp": 9999999999,
        "jti": str(uuid.uuid4()),
    }
    wrong_type_token = jwt.encode(payload, secret, algorithm="HS256")

    with pytest.raises(InvalidTokenError) as exc_info:
        verify_access_token(wrong_type_token)
    assert "Invalid token type" in str(exc_info.value)


def test_malformed_token_rejection():
    """Verify that completely malformed strings raise InvalidTokenError."""
    with pytest.raises(InvalidTokenError):
        verify_access_token("not.a.valid.jwt")

    with pytest.raises(InvalidTokenError):
        verify_access_token("")


def test_generate_and_hash_refresh_token():
    """Verify high-entropy opaque refresh token generation and SHA-256 hashing."""
    token1 = generate_refresh_token()
    token2 = generate_refresh_token()

    assert isinstance(token1, str)
    assert len(token1) >= 40
    assert token1 != token2  # High entropy randomness

    hash1 = hash_refresh_token(token1)
    hash2 = hash_refresh_token(token1)  # Deterministic hash
    hash3 = hash_refresh_token(token2)

    assert len(hash1) == 64  # SHA-256 hex is exactly 64 characters
    assert hash1 == hash2
    assert hash1 != hash3

    with pytest.raises(ValueError):
        hash_refresh_token("")
