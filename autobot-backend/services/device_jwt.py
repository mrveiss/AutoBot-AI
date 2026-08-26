# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Device-scoped JWTs for mobile device authentication (GH#9493).

Mobile devices receive a long-lived JWT after pairing (QR challenge flow)
so they can authenticate API calls without storing user passwords. Device
JWTs carry a `scope` claim ("read" or "write") and are validated against
both the JWT signature and the device record existence in the database.

Security measures (GH#9493):
1. Scope enforcement — read-scoped tokens cannot use mutating HTTP methods
2. Narrow allow-list — device JWTs only valid for /api/devices/ endpoints
3. Revocation check — validates device still exists in DB on each request

Scope registry
--------------
``VALID_SCOPES`` defines the allowed scopes for device JWTs::

    read   – GET/HEAD/OPTIONS only
    write  – All HTTP methods including POST/PUT/PATCH/DELETE

Flow
----
1. Mobile app completes pairing via POST /api/devices/pair (QR challenge).
2. Backend calls ``mint_device_jwt(device_id, user_id, scope="read")``
   and returns the token to the mobile app.
3. Mobile app includes token in ``Authorization: Bearer <device-jwt>``
   for subsequent API calls.
4. Auth middleware calls ``validate_device_jwt(token)`` on each request
   to verify signature + device existence + scope.
5. When user unpairs the device via DELETE /api/devices/{id}, the device
   row is deleted — future JWT validation fails the existence check.

Device existence cache
-----------------------
Redis key: ``device_jwt:exists:{device_id}``  TTL = 60 s (tunable)
Caches device existence checks to avoid N+1 DB queries. Cache is invalidated
on device deletion so unpaired devices cannot authenticate past cache TTL.

Configuration
-------------
``DEVICE_JWT_SECRET``       – HMAC signing secret (32+ char recommended).
                              Falls back to ``AUTOBOT_JWT_SECRET``.
``DEVICE_JWT_TTL_DAYS``     – Token lifetime in days (default 90).
``DEVICE_JWT_CACHE_TTL``    – Device existence cache TTL in seconds (default 60).
``DEVICE_JWT_AUDIENCE``     – Expected ``aud`` claim (default "autobot:device").
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Dict

from autobot_shared.auth.jwt_core import JWTDecodeError, decode_jwt, encode_jwt
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from services.audit.audit import AuditAction, audit_record

logger = get_logger(__name__)

_ENV_SECRET = "DEVICE_JWT_SECRET"  # nosec B105  # environment variable name constant, not a hardcoded secret
_ENV_TTL_DAYS = "DEVICE_JWT_TTL_DAYS"
_ENV_CACHE_TTL = "DEVICE_JWT_CACHE_TTL"
_ENV_AUDIENCE = "DEVICE_JWT_AUDIENCE"
_DEFAULT_TTL_DAYS = 90
_DEFAULT_CACHE_TTL = 60
_DEFAULT_AUDIENCE = "autobot:device"
_DEVICE_EXISTS_PREFIX = "device_jwt:exists:"

#: Allowed scopes for device JWTs (GH#9493 security requirement).
VALID_SCOPES: frozenset[str] = frozenset({"read", "write"})

#: Credential states (#14964). ``revoked`` is a row that still exists with
#: ``revoked_at`` set — soft revocation, so the pairing record and its audit
#: trail outlive the revocation. ``absent`` is a row that is simply gone
#: (the pre-#14964 unpair path, which deletes).
STATE_ACTIVE = "active"
STATE_REVOKED = "revoked"
STATE_ABSENT = "absent"
_DEVICE_STATES: frozenset[str] = frozenset({STATE_ACTIVE, STATE_REVOKED, STATE_ABSENT})


def _secret() -> str:
    """Resolve the signing secret from environment variables."""
    for var in (_ENV_SECRET, "AUTOBOT_JWT_SECRET"):
        val = os.environ.get(var, "")
        if val:
            return val
    raise RuntimeError("No device-JWT signing secret configured. Set DEVICE_JWT_SECRET (or AUTOBOT_JWT_SECRET).")


def _ttl_days() -> int:
    """Resolve TTL from ``DEVICE_JWT_TTL_DAYS`` env var, defaulting to 90 days."""
    raw = os.environ.get(_ENV_TTL_DAYS, "")
    if not raw:
        return _DEFAULT_TTL_DAYS
    try:
        return int(raw)
    except ValueError:
        logger.warning("DEVICE_JWT_TTL_DAYS=%r is not an integer; using default %d days", raw, _DEFAULT_TTL_DAYS)
        return _DEFAULT_TTL_DAYS


def _cache_ttl() -> int:
    """Resolve cache TTL from ``DEVICE_JWT_CACHE_TTL`` env var, defaulting to 60 s."""
    raw = os.environ.get(_ENV_CACHE_TTL, "")
    if not raw:
        return _DEFAULT_CACHE_TTL
    try:
        return int(raw)
    except ValueError:
        logger.warning("DEVICE_JWT_CACHE_TTL=%r is not an integer; using default %d s", raw, _DEFAULT_CACHE_TTL)
        return _DEFAULT_CACHE_TTL


def _audience() -> str:
    """Resolve the expected ``aud`` claim, defaulting to ``_DEFAULT_AUDIENCE``."""
    return os.environ.get(_ENV_AUDIENCE, "") or _DEFAULT_AUDIENCE


def mint_device_jwt(device_id: str, user_id: str, scope: str = "read") -> str:
    """Mint a long-lived device-scoped JWT.

    Args:
        device_id: UUID of the paired mobile device.
        user_id: User ID who owns the device.
        scope: Access scope ("read" or "write"). Defaults to "read" (GH#9493 least-privilege).

    Returns:
        Signed JWT string.

    Raises:
        ValueError: If scope is not in ``VALID_SCOPES``.
        RuntimeError: If no signing secret is configured.
    """
    if scope not in VALID_SCOPES:
        raise ValueError(f"Invalid scope: {scope!r}. Valid: {sorted(VALID_SCOPES)}")

    ttl_days = _ttl_days()
    payload: Dict[str, object] = {
        "aud": _audience(),
        "device_id": device_id,
        "user_id": user_id,
        "scope": scope,
    }
    token = encode_jwt(payload, secret=_secret(), expires_delta=timedelta(days=ttl_days))

    audit_record(
        user_id=user_id,
        action=AuditAction.DEVICE_JWT_MINT,
        resource_type="device_jwt",
        resource_id=device_id,
        metadata={
            "scope": scope,
            "ttl_days": ttl_days,
        },
    )
    logger.info(
        "device_jwt: minted device_id=%s user=%s scope=%s ttl=%d days",
        device_id,
        user_id,
        scope,
        ttl_days,
    )
    return token


async def _read_device_state(device_id: str) -> str:
    """Read the credential's state straight from the database (no cache)."""
    from sqlalchemy import select  # noqa: PLC0415

    from models.mobile_device import MobileDevice  # noqa: PLC0415
    from user_management.database import get_async_session  # noqa: PLC0415

    async for session in get_async_session():
        result = await session.execute(
            select(MobileDevice.revoked_at).where(MobileDevice.id == device_id).limit(1)
        )
        row = result.first()
        break  # Only need one iteration
    if row is None:
        return STATE_ABSENT
    return STATE_ACTIVE if row[0] is None else STATE_REVOKED


def _decode_cached_state(cached: object) -> str:
    """Map a cached value to a state, tolerating the pre-#14964 "1"/"0" form."""
    raw = cached.decode() if isinstance(cached, (bytes, bytearray)) else str(cached)
    if raw in _DEVICE_STATES:
        return raw
    return STATE_ACTIVE if raw == "1" else STATE_ABSENT


async def _device_state_cached(device_id: str) -> str:
    """Resolve a device credential's state, with Redis cache (GH#9493, #14964).

    Returns one of :data:`STATE_ACTIVE`, :data:`STATE_REVOKED` or
    :data:`STATE_ABSENT`. Revocation is kept distinct from absence on purpose:
    both refuse the credential, and a log that says only "refused" cannot tell
    an operator whether a device was unpaired or explicitly revoked.
    """
    redis = await get_async_redis_client(database="main")
    cache_key = _DEVICE_EXISTS_PREFIX + device_id

    if redis is not None:
        cached = await redis.get(cache_key)
        if cached is not None:
            state = _decode_cached_state(cached)
            logger.debug("device_jwt: cache hit device_id=%s state=%s", device_id, state)
            return state

    state = await _read_device_state(device_id)

    if redis is not None:
        await redis.setex(cache_key, _cache_ttl(), state)
        logger.debug("device_jwt: cache miss device_id=%s state=%s (cached)", device_id, state)

    return state


async def invalidate_device_cache(device_id: str) -> None:
    """Invalidate the device existence cache after device deletion (GH#9493).

    Call this after DELETE /api/devices/{id} to ensure the JWT validation
    fails immediately instead of accepting requests until cache TTL expires.

    Args:
        device_id: UUID of the deleted device.
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return
    cache_key = _DEVICE_EXISTS_PREFIX + device_id
    await redis.delete(cache_key)
    logger.debug("device_jwt: invalidated cache for device_id=%s", device_id)


async def validate_device_jwt(token: str) -> Dict[str, object]:
    """Validate a device-scoped JWT.

    Checks (GH#9493 / #14964 security requirements):
    1. Signature validity and expiry via ``decode_jwt``.
    2. Device still exists in the database AND has not been revoked. Both a
       deleted row and a row carrying ``revoked_at`` refuse the credential;
       the two are logged distinctly (``reason=unpaired`` vs ``reason=revoked``).

    Revoking one device sets ``revoked_at`` on that row alone, so the same
    user's other paired devices are untouched. The check runs per handshake:
    revocation takes effect on the **next** authentication, and a session
    already established stays up until it closes (a running socket is never
    re-authenticated — see ``api/ws_security.enforce_ws_remote_control_auth``).

    Args:
        token: JWT string from Authorization header.

    Returns:
        Decoded claims dict with keys: device_id, user_id, scope.

    Raises:
        JWTExpiredError: Token has passed its expiration timestamp.
        JWTDecodeError: Token has invalid signature, is malformed, or the
            device has been unpaired (device row deleted).
    """
    claims = decode_jwt(token, _secret(), audience=_audience())

    device_id = claims.get("device_id")
    if not device_id:
        raise JWTDecodeError("device_jwt: missing device_id claim")

    # GH#9493 / #14964 revocation check. Two refusals, closed the same way to
    # the caller but never conflated in the log: a deleted pairing and an
    # explicitly revoked credential are different operational events.
    state = await _device_state_cached(str(device_id))
    if state == STATE_REVOKED:
        logger.warning("device_jwt: refused device_id=%s reason=revoked", device_id)
        raise JWTDecodeError(f"device_jwt: device {device_id} has been revoked")
    if state != STATE_ACTIVE:
        logger.warning("device_jwt: refused device_id=%s reason=unpaired", device_id)
        raise JWTDecodeError(f"device_jwt: device {device_id} has been unpaired or does not exist")

    return claims
