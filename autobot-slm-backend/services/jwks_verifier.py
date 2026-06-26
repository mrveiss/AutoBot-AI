# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
JWKS verifier for the SLM backend (#10197, epic #10193).

Fetches the authority (autobot-backend) JWKS public-key set and caches it
locally.  Tokens are verified via the shared ``jwt_core.decode_jwt`` so the
algorithm-confusion guard applies on every call.

Usage::

    from services.jwks_verifier import verify_authority_token

    payload = await verify_authority_token(token)   # None on failure

Design notes
------------
- The SLM NEVER holds the signing private key.  Only the public key(s) are
  cached here (Pattern B).
- Key lookup is by ``kid`` JWT header field.  On an unknown ``kid``, the cache
  is refreshed once (handles key rotation) before giving up.
- JWKS-unreachable returns ``None`` — the caller falls back to HS256 or raises
  401.  This module never raises to the caller; all errors are logged + None.
- The async HTTP fetch uses ``httpx.AsyncClient`` (already in requirements.txt);
  no new dependency is introduced.
- The cache TTL is read from ``config.settings`` (``jwks_cache_ttl_seconds``),
  defaulting to 3600 s.  The authority base URL is ``settings.authority_base_url``.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, _peek_alg, decode_jwt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal cache — module-level singleton (never use mutable default args)
# ---------------------------------------------------------------------------

_cache_entries: Dict[str, Any] = {}  # kid -> public key object (RSA)
_cache_fetched_at: float = 0.0  # epoch seconds of last successful fetch


def _cache_expired(ttl: int) -> bool:
    """Return True when the cache is empty or older than *ttl* seconds."""
    return not _cache_entries or (time.monotonic() - _cache_fetched_at) > ttl


def _invalidate_cache() -> None:
    """Clear the in-process key cache so the next call re-fetches."""
    global _cache_fetched_at
    _cache_entries.clear()
    _cache_fetched_at = 0.0


# ---------------------------------------------------------------------------
# JWKS fetch + reconstruction
# ---------------------------------------------------------------------------


async def _fetch_jwks(url: str, timeout: float) -> Optional[Dict[str, Any]]:
    """GET *url* and return the parsed JWKS dict, or None on error."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("JWKS fetch HTTP error from %s: %s", url, exc)
        return None
    except Exception as exc:
        logger.warning("JWKS fetch failed from %s: %s", url, exc)
        return None


def _build_key_cache(jwks: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct RSA public key objects from a JWKS ``keys`` list.

    Uses PyJWT's ``RSAAlgorithm.from_jwk`` to convert ``n``/``e`` JWK values
    to a public key that ``decode_jwt(public_key=...)`` accepts.

    Returns a dict keyed by ``kid`` (falls back to ``""`` for a keyless JWK).
    """
    from jwt.algorithms import RSAAlgorithm

    result: Dict[str, Any] = {}
    for jwk in jwks.get("keys", []):
        if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
            continue
        kid = jwk.get("kid", "")
        try:
            pub_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
            result[kid] = pub_key
        except Exception as exc:
            logger.warning("Skipping invalid JWK (kid=%r): %s", kid, exc)
    return result


async def _refresh_cache(authority_url: str, timeout: float) -> bool:
    """Fetch the JWKS and rebuild the in-process cache.

    Returns True on success, False when the endpoint is unreachable or returns
    an unusable payload.
    """
    global _cache_fetched_at

    jwks = await _fetch_jwks(authority_url, timeout)
    if jwks is None:
        return False

    new_keys = _build_key_cache(jwks)
    if not new_keys:
        logger.warning("JWKS response contained no usable RSA signature keys from %s", authority_url)
        return False

    _cache_entries.clear()
    _cache_entries.update(new_keys)
    _cache_fetched_at = time.monotonic()
    logger.debug("JWKS cache refreshed: %d key(s) loaded", len(_cache_entries))
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _normalize_claims(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize authority token claims to a common SLM payload shape.

    Authority tokens carry ``username`` / ``user_id`` / ``role``.
    SLM HS256 legacy tokens carry ``sub`` / ``admin`` / ``role``.

    The returned dict always has:
      - ``sub``      — username (set from ``username`` if ``sub`` absent)
      - ``username`` — canonical username
      - ``role``     — role string (preserved as-is)
      - ``admin``    — bool derived from role (True when role == "admin")
      - ``authority_token`` — True (marks the token source)
    """
    username = payload.get("username") or payload.get("sub", "")
    role = payload.get("role", "user")
    normalized = dict(payload)
    normalized["sub"] = username
    normalized["username"] = username
    normalized["role"] = role
    normalized["admin"] = role == "admin"
    normalized["authority_token"] = True
    return normalized


async def verify_authority_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify an RS256 authority token via cached JWKS and return normalized claims.

    On any failure (JWKS unreachable, bad signature, expired, algorithm mismatch,
    or revoked jti) returns ``None`` — never raises.

    Caching (D1 #10158)
    -------------------
    Verified claims are cached in Redis (``slm:oidc:token_cache:*``) for
    ``OIDC_TOKEN_CACHE_TTL`` seconds so the JWKS verifier is not called on every
    request.  Cache misses fall through to the full verification path.

    Cross-service revocation (#10278)
    ----------------------------------
    After signature verification, the token's ``jti`` is checked against the
    shared RS256 denylist (``auth:rs256:jti:denylist:*``).  Revoked tokens are
    rejected even if the signature is otherwise valid.

    Key-rotation refresh
    --------------------
    If the token's ``kid`` is not in the JWKS cache, the cache is refreshed once.
    If the kid is still absent after refresh the token is rejected (unknown key).

    Args:
        token: RS256 JWT string from the identity authority.

    Returns:
        Normalized claims dict, or ``None`` on verification failure.
    """
    # D1 (#10158): check OIDC token claim cache before expensive JWKS verify
    from services.oidc_token_cache import cache_claims, get_cached_claims  # noqa: PLC0415

    cached = await get_cached_claims(token)
    if cached is not None:
        # Security (#10278): a cache hit must STILL honour revocation — otherwise a
        # revoked-but-cached token would bypass the denylist until the cache TTL expires.
        cached_jti = cached.get("jti")
        if cached_jti:
            from services.rs256_denylist import is_rs256_jti_revoked  # noqa: PLC0415

            try:
                if await is_rs256_jti_revoked(str(cached_jti)):
                    logger.warning("verify_authority_token: cached jti=%r is revoked — rejecting", cached_jti)
                    return None
            except Exception:  # fail-open on Redis down (matches the full-verify path)
                logger.warning("rs256 denylist check failed on cache hit; failing open", exc_info=True)
        logger.debug("verify_authority_token: cache hit (sub=%r)", cached.get("sub"))
        return cached

    from config import settings  # deferred: avoids circular import at module load

    authority_url = settings.authority_base_url.rstrip("/") + settings.authority_jwks_path
    ttl = settings.jwks_cache_ttl_seconds
    fetch_timeout = settings.jwks_fetch_timeout_seconds

    token_alg = _peek_alg(token)
    if token_alg != "RS256":  # nosec B105 - JWT algorithm identifier, not a credential
        # Called with a non-RS256 token — logic error in caller
        logger.warning("verify_authority_token called with non-RS256 token (alg=%r)", token_alg)
        return None

    import jwt as _jwt

    token_kid: Optional[str] = None
    try:
        hdr = _jwt.get_unverified_header(token)
        token_kid = hdr.get("kid")
    except Exception:
        logger.warning("Cannot decode JWT header — rejecting token")
        return None

    # Ensure cache is fresh or contains the kid
    if _cache_expired(ttl):
        await _refresh_cache(authority_url, fetch_timeout)

    # On unknown kid, attempt one refresh (key rotation)
    if token_kid not in _cache_entries:
        logger.info("Unknown kid=%r; refreshing JWKS from %s", token_kid, authority_url)
        refreshed = await _refresh_cache(authority_url, fetch_timeout)
        if not refreshed or token_kid not in _cache_entries:
            logger.warning(
                "Authority token rejected: kid=%r not found in JWKS (keys=%r)",
                token_kid,
                list(_cache_entries.keys()),
            )
            return None

    pub_key = _cache_entries[token_kid]

    try:
        payload = decode_jwt(token, public_key=pub_key, algorithms=["RS256"])
    except JWTExpiredError:
        logger.warning("Authority RS256 token expired (kid=%r)", token_kid)
        return None
    except JWTDecodeError as exc:
        logger.warning("Authority RS256 token invalid (kid=%r): %s", token_kid, exc)
        return None

    # #10278: check cross-service RS256 jti denylist (fail-open on Redis down)
    jti = payload.get("jti")
    if jti:
        from services.rs256_denylist import is_rs256_jti_revoked  # noqa: PLC0415

        try:
            if await is_rs256_jti_revoked(str(jti)):
                logger.warning("Authority RS256 token rejected: jti=%r is revoked", jti)
                return None
        except Exception:
            logger.warning("rs256 denylist check failed; failing open", exc_info=True)

    claims = _normalize_claims(payload)

    # D1 (#10158): populate OIDC token claim cache for subsequent requests
    await cache_claims(token, claims)

    return claims
