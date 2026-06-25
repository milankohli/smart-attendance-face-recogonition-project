"""
app/core/security.py
───────────────────────────────────────────────────────────────────────────────
Security utilities: password hashing and JWT access/refresh token handling.

This module provides only the CRYPTOGRAPHIC PRIMITIVES and TOKEN UTILITIES.
It does not implement the `/auth/*` endpoints, user lookup, or
`get_current_user` dependency — those belong to a later phase (the
`api/v1/auth.py` router and `services/auth_service.py`), once the `users`
model exists.

Provided here so the foundation is ready to be wired up:
  • verify_password / hash_password   — passlib (bcrypt)
  • create_access_token               — short-lived JWT for API auth
  • create_refresh_token              — longer-lived JWT for token refresh
  • decode_token                      — verify + decode any JWT issued above
───────────────────────────────────────────────────────────────────────────────
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password hashing ───────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage (e.g. in `users.hashed_password`)."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against its stored bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWT token creation ────────────────────────────────────────────────────
TokenType = Literal["access", "refresh"]


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Internal helper: build and sign a JWT.

    Standard claims included:
      sub  – token subject (typically the user id / username)
      type – "access" or "refresh" (lets dependencies reject the wrong type)
      iat  – issued-at timestamp
      exp  – expiry timestamp
    """
    now = datetime.now(timezone.utc)
    to_encode: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    Create a short-lived access token.

    `subject` is typically the user's id (as a string). `extra_claims`
    can carry non-sensitive info such as role, e.g. {"role": "admin"},
    to avoid a DB lookup on every request (future phases may still choose
    to re-verify against the DB for critical operations).
    """
    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_refresh_token(subject: str) -> str:
    """Create a longer-lived refresh token used to obtain new access tokens."""
    return _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT (access or refresh).

    Returns the decoded claims dict.

    Raises
    ------
    jose.JWTError if the token is invalid, malformed, or expired.
    Callers (future `get_current_user` dependency) should catch this and
    raise an HTTP 401.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise
