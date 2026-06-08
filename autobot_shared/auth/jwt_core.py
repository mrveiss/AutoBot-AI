# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared JWT encode/decode core and bcrypt password helpers (#3840).

Both autobot-backend (auth_middleware.py) and autobot-slm-backend
(services/auth.py) duplicated identical jwt.encode/jwt.decode and bcrypt
call sites.  This module is the single implementation; both backends import
from here.

Design decisions:
- ``encode_jwt`` / ``decode_jwt`` are thin, stateless functions that accept
  the secret as an explicit argument so each backend can supply its own key
  without this module touching environment variables or config objects.
- ``decode_jwt`` distinguishes expiry from other decode failures via the two
  typed exceptions below, letting callers log each case appropriately.
- The algorithm is hard-coded to HS256 because neither backend ever changed
  it; if that changes in the future the parameter can be promoted.
- Password helpers are included because both backends contained byte-for-byte
  identical bcrypt wrappers.

Usage (backend)::

    from autobot_shared.auth.jwt_core import encode_jwt, decode_jwt

    token = encode_jwt(payload, secret=jwt_secret)
    data   = decode_jwt(token,   secret=jwt_secret)  # raises on failure

Usage (slm-backend)::

    from autobot_shared.auth.jwt_core import encode_jwt, decode_jwt

    token = encode_jwt({"sub": username, "exp": expire}, secret=settings.secret_key)
    data   = decode_jwt(token, secret=settings.secret_key)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


class JWTDecodeError(Exception):
    """Raised when a token is structurally invalid or the signature does not match."""


class JWTExpiredError(JWTDecodeError):
    """Raised when a token is structurally valid but has expired."""


def encode_jwt(
    payload: Dict[str, Any],
    secret: str,
    expires_delta: timedelta | None = None,
    expiry_hours: float | None = None,
) -> str:
    """Encode *payload* as a signed HS256 JWT.

    Expiry precedence (first truthy value wins):
    1. ``exp`` key already present in *payload*
    2. ``expires_delta`` argument
    3. ``expiry_hours`` argument  (converted to ``timedelta``)
    4. No expiry set (token never expires — use only for service tokens)

    Args:
        payload: Claims dict.  A copy is taken; the caller's dict is not mutated.
        secret: HMAC signing secret.
        expires_delta: Optional explicit TTL.
        expiry_hours: Optional TTL expressed as a float number of hours.

    Returns:
        Signed JWT string.
    """
    to_encode = payload.copy()

    if "exp" not in to_encode:
        if expires_delta is not None:
            to_encode["exp"] = datetime.now(tz=timezone.utc) + expires_delta
        elif expiry_hours is not None:
            to_encode["exp"] = datetime.now(tz=timezone.utc) + timedelta(hours=expiry_hours)

    return jwt.encode(to_encode, secret, algorithm=_ALGORITHM)


def decode_jwt(token: str, secret: str, audience: str | None = None) -> Dict[str, Any]:
    """Decode and verify a signed HS256 JWT.

    Args:
        token: JWT string.
        secret: HMAC signing secret.
        audience: Expected ``aud`` claim value.  When provided, PyJWT enforces
            that the token's ``aud`` matches; a missing or mismatched audience
            raises ``JWTDecodeError``.  When ``None`` (default), audience
            verification is skipped for backward compatibility with tokens that
            do not carry an ``aud`` claim.

    Returns:
        Decoded claims dict.

    Raises:
        JWTExpiredError: The token signature is valid but the token has expired.
        JWTDecodeError: The token is invalid for any other reason (bad signature,
            malformed header/payload, unknown algorithm, audience mismatch, etc.).
    """
    try:
        if audience is not None:
            return jwt.decode(token, secret, algorithms=[_ALGORITHM], audience=audience)
        return jwt.decode(token, secret, algorithms=[_ALGORITHM], options={"verify_aud": False})
    except ExpiredSignatureError as exc:
        raise JWTExpiredError("JWT token has expired") from exc
    except InvalidTokenError as exc:
        raise JWTDecodeError(f"JWT token is invalid: {exc}") from exc


def decode_jwt_no_verify_exp(token: str, secret: str) -> Dict[str, Any]:
    """Decode a JWT without verifying expiry — for use in refresh-token flows only.

    Callers MUST perform their own grace-period check on the ``exp`` claim.
    This function still validates the signature and algorithm so a tampered
    token is rejected.

    Args:
        token: JWT string.
        secret: HMAC signing secret.

    Returns:
        Decoded claims dict (expiry not enforced).

    Raises:
        JWTDecodeError: The token is structurally invalid or the signature does
            not match.
    """
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            options={"verify_exp": False},
        )
    except InvalidTokenError as exc:
        raise JWTDecodeError(f"JWT token is invalid: {exc}") from exc


def decode_jwt_or_none(token: str, secret: str) -> Dict[str, Any] | None:
    """Decode a JWT, returning ``None`` on any failure instead of raising.

    Convenience wrapper for call sites that prefer ``None``-on-failure
    (mirrors the original pattern in both backends).

    Expiry and invalid-signature failures are both logged at WARNING level
    so they remain visible in production logs without propagating exceptions.

    Args:
        token: JWT string.
        secret: HMAC signing secret.

    Returns:
        Decoded claims dict, or ``None`` if the token is invalid or expired.
    """
    try:
        return decode_jwt(token, secret)
    except JWTExpiredError:
        logger.warning("JWT token expired")
        return None
    except JWTDecodeError as exc:
        logger.warning("Invalid JWT token: %s", exc)
        return None


def hash_password(password: str) -> str:
    """Hash *password* with bcrypt (cost factor 12).

    Args:
        password: Plaintext password.

    Returns:
        Bcrypt hash string.
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify *password* against a bcrypt *hashed* value.

    Args:
        password: Plaintext candidate.
        hashed: Stored bcrypt hash.

    Returns:
        ``True`` if the password matches, ``False`` otherwise (including on
        any internal bcrypt error).
    """
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception as exc:
        logger.error("Password verification error: %s", exc)
        return False
