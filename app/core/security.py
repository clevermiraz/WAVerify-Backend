"""Password hashing, JWT issuing/verification and API key generation."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenError

API_KEY_PREFIX = "wav_"
# bcrypt hashes at most the first 72 bytes of input and silently ignores the
# rest, so longer passwords are rejected rather than truncated.
_MAX_PASSWORD_BYTES = 72
_API_KEY_BYTES = 24


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"


# --- Passwords -----------------------------------------------------------


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    encoded = plain.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, hashed.encode("utf-8"))
    except ValueError:
        # Malformed stored hash — treat as a failed login rather than a 500.
        return False


# --- JWT -----------------------------------------------------------------


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return `(encoded_token, jti)`."""
    now = datetime.now(UTC)
    jti = uuid4().hex
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), jti


def create_access_token(subject: str, **claims: Any) -> str:
    token, _ = _create_token(
        subject,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        claims or None,
    )
    return token


def create_refresh_token(subject: str) -> tuple[str, str]:
    return _create_token(
        subject,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_email_verification_token(subject: str) -> str:
    token, _ = _create_token(
        subject,
        TokenType.EMAIL_VERIFY,
        timedelta(hours=settings.EMAIL_TOKEN_EXPIRE_HOURS),
    )
    return token


def create_password_reset_token(subject: str, password_hash: str) -> str:
    # Binding the token to a fingerprint of the current password hash makes
    # every outstanding reset link single-use: once the password changes the
    # fingerprint no longer matches.
    token, _ = _create_token(
        subject,
        TokenType.PASSWORD_RESET,
        timedelta(hours=settings.PASSWORD_RESET_EXPIRE_HOURS),
        {"fp": _fingerprint(password_hash)},
    )
    return token


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def password_reset_fingerprint(password_hash: str) -> str:
    return _fingerprint(password_hash)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError()
    if not payload.get("sub"):
        raise InvalidTokenError()
    return payload


# --- API keys ------------------------------------------------------------


def generate_api_key() -> tuple[str, str, str]:
    """Return `(plaintext_key, sha256_hash, display_prefix)`.

    The plaintext is shown exactly once at creation time; only the hash is
    persisted, so a database leak cannot yield working credentials.
    """
    env = "live" if settings.is_production else "test"
    raw = secrets.token_urlsafe(_API_KEY_BYTES)
    key = f"{API_KEY_PREFIX}{env}_{raw}"
    return key, hash_api_key(key), key[:12]


def hash_api_key(key: str) -> str:
    # SHA-256 rather than bcrypt: API keys are high-entropy random strings,
    # so a fast hash is safe here and lets us look keys up by an indexed
    # column on every request.
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
