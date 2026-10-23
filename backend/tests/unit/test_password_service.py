"""Unit tests for password security, Argon2id hashing, bcrypt fallback, and policy validation."""

import logging
import pytest
import bcrypt

from app.services.auth.password import (
    PasswordPolicyError,
    hash_password,
    needs_rehash,
    validate_password_policy,
    verify_password,
)
from app.models.user import User


def test_password_hashes_successfully_with_argon2id():
    """Verify that hash_password creates a valid Argon2id hash."""
    plain = "CorrectHorseBatteryStaple123"
    pw_hash = hash_password(plain)

    assert pw_hash.startswith("$argon2id$")
    assert plain not in pw_hash  # Plaintext is not stored as plain


def test_password_verifies_correctly():
    """Verify that correct password returns True and incorrect password returns False."""
    plain = "SecureP@ssw0rd!2026"
    pw_hash = hash_password(plain)

    # Correct password
    assert verify_password(plain, pw_hash) is True

    # Incorrect password
    assert verify_password("WrongPassword!", pw_hash) is False
    assert verify_password("securep@ssw0rd!2026", pw_hash) is False  # Case sensitive


def test_empty_or_invalid_password_policy():
    """Verify password policy rejects empty, None, short, or excessively long passwords."""
    with pytest.raises(PasswordPolicyError) as exc_1:
        validate_password_policy("")
    assert "non-empty string" in str(exc_1.value)

    with pytest.raises(PasswordPolicyError) as exc_2:
        validate_password_policy(None)  # type: ignore
    assert "non-empty string" in str(exc_2.value)

    with pytest.raises(PasswordPolicyError) as exc_3:
        validate_password_policy("short")  # Default min is 8
    assert "at least 8 characters" in str(exc_3.value)

    with pytest.raises(PasswordPolicyError) as exc_4:
        validate_password_policy("a" * 150, max_length=128)
    assert "exceeds maximum allowed length" in str(exc_4.value)

    # hash_password invokes policy validation
    with pytest.raises(PasswordPolicyError):
        hash_password("tiny")


def test_bcrypt_fallback_verification():
    """Verify that legacy/fallback bcrypt hashes are correctly verified."""
    plain = "LegacyBcryptPassword123"
    salt = bcrypt.gensalt(rounds=12)
    bcrypt_hash = bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")

    assert bcrypt_hash.startswith("$2b$")
    assert verify_password(plain, bcrypt_hash) is True
    assert verify_password("WrongPassword123", bcrypt_hash) is False


def test_needs_rehash_detection():
    """Verify needs_rehash identifies bcrypt hashes and fresh Argon2id hashes."""
    plain = "TestPassword456!"
    argon_hash = hash_password(plain)
    assert needs_rehash(argon_hash) is False

    salt = bcrypt.gensalt(rounds=10)
    bcrypt_hash = bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")
    assert needs_rehash(bcrypt_hash) is True

    assert needs_rehash("") is False
    assert needs_rehash(None) is False  # type: ignore


def test_malformed_hash_verification_safety():
    """Verify verify_password safely returns False for corrupted or unexpected hashes."""
    assert verify_password("password123", "") is False
    assert verify_password("", "somehash") is False
    assert verify_password("password123", "corrupted$hash$value") is False
    assert verify_password("password123", "$argon2id$v=19$m=0,t=0,p=0$corrupted") is False


def test_password_never_appears_in_logs_or_user_repr(caplog):
    """Verify that password operations do not leak passwords in logs or string representations."""
    caplog.set_level(logging.DEBUG)

    plain = "TopSecretPassword999!"
    pw_hash = hash_password(plain)
    verify_password(plain, pw_hash)

    # Check logs
    for record in caplog.records:
        assert plain not in record.message

    # Check User model representation
    user = User(
        email="test@company.local",
        password_hash=pw_hash,
        display_name="Test User",
    )
    user_repr = repr(user)
    assert plain not in user_repr
    assert pw_hash not in user_repr
