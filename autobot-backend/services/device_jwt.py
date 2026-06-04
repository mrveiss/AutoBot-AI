# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
from services.audit.unified_audit import AuditAction, audit_record

logger = get_logger(__name__)

_ENV_SECRET = "DEVICE_JWT_SECRET"
_ENV_TTL_DAYS = "DEVICE_JWT_TTL_DAYS"
_ENV_CACHE_TTL = "DEVICE_JWT_CACHE_TTL"
_ENV_AUDIENCE = "DEVICE_JWT_AUDIENCE"
_DEFAULT_TTL_DAYS = 90
_DEFAULT_CACHE_TTL = 60
_DEFAULT_AUDIENCE = "autobot:device"
_DEVICE_EXISTS_PREFIX = "device_jwt:exists:"

#: Allowed scopes for device JWTs (GH#9493 security requirement).
VALID_SCOPES: frozenset[str] = frozenset({"read", "write"})


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


async def _device_exists_cached(device_id: str) -> bool:
    """Check if device exists in DB, with Redis cache (GH#9493 revocation check).

    Returns:
        True if the device row exists in the database, False otherwise.
    """
    redis = await get_async_redis_client(database="main")
    cache_key = _DEVICE_EXISTS_PREFIX + device_id

    # Try cache first
    if redis is not None:
        cached = await redis.get(cache_key)
        if cached is not None:
            exists = cached.decode() == "1" if isinstance(cached, bytes) else cached == "1"
            logger.debug("device_jwt: cache hit device_id=%s exists=%s", device_id, exists)
            return exists

    # Cache miss — query DB
    from sqlalchemy import select

    from autobot_shared.database_connection import async_session_maker
    from models.mobile_device import MobileDevice

    async with async_session_maker() as session:
        result = await session.execute(select(MobileDevice.id).where(MobileDevice.id == device_id).limit(1))
        exists = result.scalar_one_or_none() is not None

    # Write to cache
    if redis is not None:
        await redis.setex(cache_key, _cache_ttl(), "1" if exists else "0")
        logger.debug("device_jwt: cache miss device_id=%s exists=%s (cached)", device_id, exists)

    return exists


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

    Checks (GH#9493 security requirements):
    1. Signature validity and expiry via ``decode_jwt``.
    2. Device still exists in the database (revocation check).

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

    # GH#9493 revocation check: verify device still exists
    if not await _device_exists_cached(str(device_id)):
        raise JWTDecodeError(f"device_jwt: device {device_id} has been unpaired or does not exist")

    return claims
