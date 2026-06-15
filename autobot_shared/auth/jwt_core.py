# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared JWT encode/decode core and bcrypt password helpers (#3840, #10196).

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
- RS256 support (#10196): the identity authority (autobot-backend) signs new
  tokens with an RSA private key.  Consumer services verify using only the
  public key fetched from the JWKS endpoint.  Legacy HS256 tokens (signed
  before the upgrade) are still accepted via a graceful fallback so in-flight
  sessions are not invalidated.
- Algorithm-confusion prevention: the verification path reads the ``alg``
  header from the token and matches it against an explicit allow-list.  An
  RS256 token is NEVER verified with an HS256 secret, and vice-versa.
  ``alg=none`` is blocked by always passing ``algorithms=[...]`` to PyJWT.
- Password helpers are included because both backends contained byte-for-byte
  identical bcrypt wrappers.

Usage (HS256 — unchanged default)::

    from autobot_shared.auth.jwt_core import encode_jwt, decode_jwt

    token = encode_jwt(payload, secret=jwt_secret)
    data   = decode_jwt(token,   secret=jwt_secret)  # raises on failure

Usage (RS256 — identity authority)::

    from autobot_shared.auth.jwt_core import encode_jwt, decode_jwt

    token = encode_jwt(payload, private_key=pem_str, algorithm="RS256", kid="autobot-1")
    data  = decode_jwt(token,   public_key=pem_str,  algorithms=["RS256"])

Usage (dual-accept — consumer that accepts both during migration)::

    from autobot_shared.auth.jwt_core import decode_jwt_multi

    data = decode_jwt_multi(token, public_key=pem_pub, hs256_secret=legacy_secret)

Usage (slm-backend — HS256 unchanged)::

    token = encode_jwt({"sub": username, "exp": expire}, secret=settings.secret_key)
    data   = decode_jwt(token, secret=settings.secret_key)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_ALGORITHM_RS256 = "RS256"
_ALLOWED_ALGORITHMS = frozenset({"HS256", "RS256"})


class JWTDecodeError(Exception):
    """Raised when a token is structurally invalid or the signature does not match."""


class JWTExpiredError(JWTDecodeError):
    """Raised when a token is structurally valid but has expired."""


def _peek_alg(token: str) -> str | None:
    """Return the ``alg`` header value from *token* without verifying the signature.

    Used to route verification to the correct key type before calling PyJWT.
    Returns ``None`` if the header cannot be decoded (malformed token).

    Security note: the algorithm is read from the *unverified* header.  We only
    use it to select the verification key; PyJWT's own ``algorithms=`` guard
    re-checks the header value against the allow-list during verification so a
    tampered algorithm header cannot bypass signature validation.
    """
    try:
        unverified = jwt.get_unverified_header(token)
        return unverified.get("alg")
    except Exception:
        return None


def encode_jwt(
    payload: Dict[str, Any],
    secret: str | None = None,
    private_key: str | None = None,
    algorithm: str = _ALGORITHM,
    kid: str | None = None,
    expires_delta: timedelta | None = None,
    expiry_hours: float | None = None,
) -> str:
    """Encode *payload* as a signed JWT.

    Supports both HS256 (legacy / SLM) and RS256 (identity authority).

    Expiry precedence (first truthy value wins):
    1. ``exp`` key already present in *payload*
    2. ``expires_delta`` argument
    3. ``expiry_hours`` argument  (converted to ``timedelta``)
    4. No expiry set (token never expires — use only for service tokens)

    Args:
        payload: Claims dict.  A copy is taken; the caller's dict is not mutated.
        secret: HMAC signing secret.  Required when ``algorithm="HS256"``.
        private_key: PEM-encoded RSA private key string.  Required when
            ``algorithm="RS256"``.
        algorithm: JWT algorithm — ``"HS256"`` (default) or ``"RS256"``.
        kid: Key ID to embed in the JWT header.  Only used for RS256.
        expires_delta: Optional explicit TTL.
        expiry_hours: Optional TTL expressed as a float number of hours.

    Returns:
        Signed JWT string.

    Raises:
        ValueError: If neither ``secret`` nor ``private_key`` is supplied, or
            if an unsupported ``algorithm`` is requested.
    """
    if algorithm not in _ALLOWED_ALGORITHMS:
        raise ValueError(f"Unsupported algorithm {algorithm!r}. Allowed: {sorted(_ALLOWED_ALGORITHMS)}")

    to_encode = payload.copy()

    if "exp" not in to_encode:
        if expires_delta is not None:
            to_encode["exp"] = datetime.now(tz=timezone.utc) + expires_delta
        elif expiry_hours is not None:
            to_encode["exp"] = datetime.now(tz=timezone.utc) + timedelta(hours=expiry_hours)

    if algorithm == _ALGORITHM_RS256:
        if not private_key:
            raise ValueError("private_key is required for RS256 encoding")
        headers: Dict[str, Any] = {}
        if kid:
            headers["kid"] = kid
        return jwt.encode(to_encode, private_key, algorithm=_ALGORITHM_RS256, headers=headers or None)

    # HS256 path — unchanged behaviour for all existing callers
    if not secret:
        raise ValueError("secret is required for HS256 encoding")
    return jwt.encode(to_encode, secret, algorithm=_ALGORITHM)


def decode_jwt(
    token: str,
    secret: str | None = None,
    public_key: str | None = None,
    algorithms: List[str] | None = None,
    audience: str | None = None,
) -> Dict[str, Any]:
    """Decode and verify a signed JWT.

    Supports both HS256 (legacy / SLM) and RS256 (identity authority).

    Algorithm-confusion prevention
    --------------------------------
    The ``alg`` header is read from the token before verification and compared
    against the ``algorithms`` allow-list passed to PyJWT.  An RS256 token is
    **never** verified with an HS256 secret: if the token's ``alg`` is RS256
    but ``public_key`` is absent (or vice-versa), ``JWTDecodeError`` is raised
    before PyJWT is called.  ``alg=none`` is blocked because PyJWT requires an
    explicit non-empty algorithms list.

    Args:
        token: JWT string.
        secret: HMAC signing secret.  Required for HS256 tokens when
            ``algorithms`` does not include RS256 only.
        public_key: PEM-encoded RSA public key string.  Required for RS256
            tokens.
        algorithms: Explicit allow-list passed to PyJWT.  Defaults to
            ``["HS256"]`` when only ``secret`` is provided, and to ``["RS256"]``
            when only ``public_key`` is provided.  The caller may pass
            ``["HS256", "RS256"]`` to accept either, but must also supply the
            appropriate key for the algorithm the token actually uses.
        audience: Expected ``aud`` claim value.

    Returns:
        Decoded claims dict.

    Raises:
        JWTExpiredError: The token signature is valid but the token has expired.
        JWTDecodeError: The token is invalid for any other reason (bad signature,
            malformed header/payload, unknown algorithm, audience mismatch,
            algorithm-confusion attempt, etc.).
    """
    # Resolve default algorithms from whichever key was supplied
    if algorithms is None:
        if public_key and not secret:
            algorithms = [_ALGORITHM_RS256]
        else:
            algorithms = [_ALGORITHM]

    # Validate that the algorithm list only contains supported values
    unsupported = [a for a in algorithms if a not in _ALLOWED_ALGORITHMS]
    if unsupported:
        raise JWTDecodeError(f"Unsupported algorithms requested: {unsupported!r}")

    # --- Algorithm-confusion guard -------------------------------------------
    # Read the unverified header to select the correct verification key.
    # PyJWT will re-validate the header against `algorithms` during decode,
    # so this peek is only used to route to the right key.
    token_alg = _peek_alg(token)
    if token_alg is None:
        raise JWTDecodeError("JWT token is invalid: cannot decode header")

    if token_alg not in algorithms:
        raise JWTDecodeError(
            f"JWT algorithm mismatch: token uses {token_alg!r} "
            f"but allowed algorithms are {algorithms!r}"
        )

    if token_alg == _ALGORITHM_RS256:
        if not public_key:
            raise JWTDecodeError(
                "RS256 token presented but no public_key supplied for verification — "
                "algorithm-confusion guard rejected"
            )
        key: Any = public_key
    else:
        # HS256 (or any future HMAC variant)
        if not secret:
            raise JWTDecodeError(
                f"{token_alg} token presented but no secret supplied for verification — "
                "algorithm-confusion guard rejected"
            )
        key = secret
    # -------------------------------------------------------------------------

    try:
        if audience is not None:
            return jwt.decode(token, key, algorithms=algorithms, audience=audience)
        return jwt.decode(token, key, algorithms=algorithms, options={"verify_aud": False})
    except ExpiredSignatureError as exc:
        raise JWTExpiredError("JWT token has expired") from exc
    except InvalidTokenError as exc:
        raise JWTDecodeError(f"JWT token is invalid: {exc}") from exc


def decode_jwt_no_verify_exp(
    token: str,
    secret: str | None = None,
    public_key: str | None = None,
    algorithms: List[str] | None = None,
) -> Dict[str, Any]:
    """Decode a JWT without verifying expiry — for use in refresh-token flows only.

    Callers MUST perform their own grace-period check on the ``exp`` claim.
    This function still validates the signature and algorithm so a tampered
    token is rejected.

    The algorithm-confusion guard from ``decode_jwt`` applies here too.

    Args:
        token: JWT string.
        secret: HMAC signing secret (HS256 tokens).
        public_key: PEM-encoded RSA public key string (RS256 tokens).
        algorithms: Explicit allow-list.  Defaults to ``["HS256"]`` or
            ``["RS256"]`` based on which key is supplied.

    Returns:
        Decoded claims dict (expiry not enforced).

    Raises:
        JWTDecodeError: The token is structurally invalid, the signature does
            not match, or an algorithm-confusion attempt was detected.
    """
    if algorithms is None:
        if public_key and not secret:
            algorithms = [_ALGORITHM_RS256]
        else:
            algorithms = [_ALGORITHM]

    unsupported = [a for a in algorithms if a not in _ALLOWED_ALGORITHMS]
    if unsupported:
        raise JWTDecodeError(f"Unsupported algorithms requested: {unsupported!r}")

    # Algorithm-confusion guard (same logic as decode_jwt)
    token_alg = _peek_alg(token)
    if token_alg is None:
        raise JWTDecodeError("JWT token is invalid: cannot decode header")

    if token_alg not in algorithms:
        raise JWTDecodeError(
            f"JWT algorithm mismatch: token uses {token_alg!r} "
            f"but allowed algorithms are {algorithms!r}"
        )

    if token_alg == _ALGORITHM_RS256:
        if not public_key:
            raise JWTDecodeError("RS256 token presented but no public_key supplied — algorithm-confusion guard rejected")
        key: Any = public_key
    else:
        if not secret:
            raise JWTDecodeError(f"{token_alg} token presented but no secret supplied — algorithm-confusion guard rejected")
        key = secret

    try:
        return jwt.decode(
            token,
            key,
            algorithms=algorithms,
            options={"verify_exp": False},
        )
    except InvalidTokenError as exc:
        raise JWTDecodeError(f"JWT token is invalid: {exc}") from exc


def decode_jwt_or_none(
    token: str,
    secret: str | None = None,
    public_key: str | None = None,
    algorithms: List[str] | None = None,
) -> Dict[str, Any] | None:
    """Decode a JWT, returning ``None`` on any failure instead of raising.

    Convenience wrapper for call sites that prefer ``None``-on-failure.
    Expiry and invalid-signature failures are both logged at WARNING level.

    For backward compatibility, the positional form ``decode_jwt_or_none(token, secret)``
    continues to work (``secret`` accepts both positional and keyword).

    Args:
        token: JWT string.
        secret: HMAC signing secret (HS256 tokens).
        public_key: PEM-encoded RSA public key string (RS256 tokens).
        algorithms: Explicit allow-list.

    Returns:
        Decoded claims dict, or ``None`` if the token is invalid or expired.
    """
    try:
        return decode_jwt(token, secret=secret, public_key=public_key, algorithms=algorithms)
    except JWTExpiredError:
        logger.warning("JWT token expired")
        return None
    except JWTDecodeError as exc:
        logger.warning("Invalid JWT token: %s", exc)
        return None


def decode_jwt_multi(
    token: str,
    public_key: str,
    hs256_secret: str,
) -> Dict[str, Any]:
    """Verify a JWT that may be RS256 (new) or HS256 (legacy), auto-routing by ``alg`` header.

    This is the dual-accept helper for the identity authority's verify path
    during the migration window.  It prevents algorithm-confusion by routing
    each token to the correct key based on its own ``alg`` header.

    Args:
        token: JWT string.
        public_key: PEM-encoded RSA public key (used for RS256 tokens).
        hs256_secret: HMAC secret (used for HS256 legacy tokens).

    Returns:
        Decoded claims dict.

    Raises:
        JWTExpiredError: Token has expired.
        JWTDecodeError: Token is invalid or algorithm-confusion was detected.
    """
    token_alg = _peek_alg(token)
    if token_alg is None:
        raise JWTDecodeError("JWT token is invalid: cannot decode header")

    if token_alg == _ALGORITHM_RS256:
        return decode_jwt(token, public_key=public_key, algorithms=[_ALGORITHM_RS256])

    if token_alg == _ALGORITHM:
        logger.warning(
            "Accepted legacy HS256 JWT — token was issued before RS256 migration; "
            "encourage client to re-login to receive a new RS256 token"
        )
        return decode_jwt(token, secret=hs256_secret, algorithms=[_ALGORITHM])

    raise JWTDecodeError(f"JWT uses unsupported algorithm {token_alg!r}")


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
