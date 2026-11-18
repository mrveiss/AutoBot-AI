# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A device JWT is void once its owner's revocation marker postdates it (#20446).

The token's ``user_id`` claim is the pairing user's id (``mobile_devices.user_id``,
a plain string with no foreign key). The password-epoch marker is keyed by
USERNAME, so the claim is resolved to a username first:

- a UUID is a database user's id: the username is read from the users table, and
  an owner with no row (hard-deleted) or a soft-deleted row is REFUSED;
- anything else is a config-based account whose id *is* its username (the
  backend's built-in admin), which has no row to resolve or to find deleted.

The marker check itself is the shared gate (``auth_revocation``): no store
access of this module's own for markers, so it follows wherever that gate reads.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from auth_revocation import reject_if_revoked_by_password_change
from autobot_shared.auth.jwt_core import JWTDecodeError
from autobot_shared.auth.revocation_unavailable import revocation_unavailable_error
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

_OWNER_PREFIX = "device_jwt:owner:"
#: Cached verdict for "this id names no usable user"; a username is never empty.
_NO_OWNER = ""


def _as_user_uuid(user_id: str) -> uuid.UUID | None:
    """The UUID *user_id* spells, or ``None`` when it is a plain username."""
    try:
        return uuid.UUID(user_id)
    except ValueError:
        return None


async def _read_owner_username(owner_id: uuid.UUID) -> str:
    """Username of the live user *owner_id*, or ``_NO_OWNER`` (no row, or soft-deleted)."""
    from sqlalchemy import select  # noqa: PLC0415

    from user_management.database import get_async_session  # noqa: PLC0415
    from user_management.models.user import User  # noqa: PLC0415

    try:
        async for session in get_async_session():
            row = (await session.execute(select(User.username, User.deleted_at).where(User.id == owner_id))).first()
            break
    except Exception as exc:  # the owner cannot be placed: neither "deleted" nor "fine"
        logger.error("device_jwt: owner lookup failed (%s); denying", type(exc).__name__)
        raise revocation_unavailable_error() from exc
    return _NO_OWNER if row is None or row.deleted_at is not None else row.username


async def _owner_username(user_id: str) -> str:
    """The username owning *user_id* (cached), or ``_NO_OWNER``."""
    owner_id = _as_user_uuid(user_id)
    if owner_id is None:
        return user_id
    from services.device_jwt import _cache_ttl  # noqa: PLC0415 -- the one TTL knob; device_jwt imports this module

    redis = await get_async_redis_client(database="main")
    key = _OWNER_PREFIX + str(owner_id)
    if redis is not None and (cached := await redis.get(key)) is not None:
        return cached.decode() if isinstance(cached, (bytes, bytearray)) else str(cached)
    username = await _read_owner_username(owner_id)
    if redis is not None:
        await redis.setex(key, _cache_ttl(), username)
    return username


async def reject_if_owner_revoked(claims: dict) -> None:
    """Refuse a device token whose owner is gone or whose owner's marker postdates it.

    Raises ``JWTDecodeError`` (owner gone, or token revoked) or the shared 503 when the
    marker store cannot answer.
    """
    user_id = str(claims.get("user_id") or "")
    username = await _owner_username(user_id) if user_id else _NO_OWNER
    if username == _NO_OWNER:
        logger.warning("device_jwt: refused device_id=%s reason=owner_unresolvable", claims.get("device_id"))
        raise JWTDecodeError("device_jwt: the device's owner does not exist")
    try:
        await reject_if_revoked_by_password_change({"username": username, "iat": claims.get("iat")})
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            raise
        logger.warning("device_jwt: refused device_id=%s reason=owner_revoked", claims.get("device_id"))
        raise JWTDecodeError("device_jwt: the owner's sessions were revoked after this token was issued") from exc
