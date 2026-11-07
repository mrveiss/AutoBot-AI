# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two named postures of the one session-ownership validator (#14016).

``security.session_ownership.validate_session_ownership`` is the only validator. It takes a
``SessionPosture``:

* ``DEFAULT`` -- the flag-aware chat posture: auth-disabled and enforcement-mode fast paths,
  ``log_only`` rollout, org-admin and shared-session grants, legacy claim of an unowned session.
* ``STRICT`` -- the conversation-file posture, which never consults a flag: a role is required,
  a global admin is allowed, everyone else must be the recorded owner, and there are no shared or
  org grants. An existing session with no owner is admin-only and is NOT claimed (#20025).

Any failure of the durable owner lookup denies under both postures (#14033), with 403 and nothing
claimed: ``SessionOwnerUnreadable``, any other exception, a missing chat-history manager, and a
recorded owner that is not a string alike. "Unknown" is never "unowned"; an ``except`` that returns
``None`` from that lookup is a fail-open. The Redis ownership cache is not covered: a Redis error
there only sends the check on to the durable lookup.

``posture`` is hidden from FastAPI, so a client can never choose it, and it must be a
``SessionPosture`` -- anything else is a ``TypeError``, never a silent ``DEFAULT``. A new private
ownership validator beside this one is a finding.

Its own module because ``session_ownership.py`` is at its recorded size ceiling (#14236).
"""

from __future__ import annotations

import enum
from typing import Dict

from fastapi import HTTPException, Request

from auth_middleware import resolve_human_user
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from utils.catalog_http_exceptions import raise_internal_error

logger = get_logger(__name__)


class SessionPosture(enum.Enum):
    """Which rules ``validate_session_ownership`` applies."""

    DEFAULT = "default"
    STRICT = "strict"


class NotSessionOwner(HTTPException):
    """STRICT's 403 for a session another user owns -- a 403 to every caller, a 404 only where a route says so.

    A subclass, so its status, detail and every ``except HTTPException`` are unchanged. The owner routes of the
    conversation files catch it to answer 404 (the same as an unknown id), so a caller cannot learn that a
    conversation exists (#20195). It is never raised for an unreadable owner (a store failure stays 403, #14033).
    """

    def __init__(self) -> None:
        super().__init__(status_code=403, detail="Access denied: You do not own this session")


async def authenticated_user(session_id: str, request: Request) -> Dict:
    """The authenticated user from the request, or 401 -- a revoked JWT included (#18688)."""
    user_data = await resolve_human_user(request)
    if not user_data:
        logger.warning("Unauthenticated access attempt to session %s...", session_id[:8])
        raise HTTPException(status_code=401, detail="Authentication required to access conversations")
    return user_data


#: A store failure, which a route must not present as "no such session" to the real owner.
UNREADABLE_OWNER_DETAIL = "Cannot verify session ownership"


def deny_unreadable_owner(session_id: str, username: str | None) -> HTTPException:
    """The one denial for an owner that cannot be read: not evidence of "unowned" (#14033)."""
    logger.warning("Ownership unreadable for session %s... - denying %s", session_id[:8], username)
    return HTTPException(status_code=403, detail=UNREADABLE_OWNER_DETAIL)


def require_posture(posture: object) -> SessionPosture:
    """*posture* itself; anything else (e.g. the string "strict") is a bug, not a silent DEFAULT."""
    if not isinstance(posture, SessionPosture):
        raise TypeError(f"posture must be a SessionPosture, not {type(posture).__name__}")
    return posture


async def read_owner(session_id: str, request: Request, username: str | None = None) -> str | None:
    """The durable owner as recorded: None when none is. Every failure to learn it denies (#14033).

    A raising lookup, no manager, or a recorded owner that is not a string is an unknown owner, and
    an unknown owner is never "unowned" -- claiming it would hand the session to the caller.
    An empty string is returned as recorded: STRICT denies it, DEFAULT reads it as unowned.
    """
    from utils.chat_utils import get_chat_history_manager  # noqa: PLC0415

    try:
        owner = await get_chat_history_manager(request).get_session_owner(session_id)
    except Exception as exc:
        logger.warning("Could not read the durable owner of session %s...: %s", session_id[:8], exc)
        raise deny_unreadable_owner(session_id, username) from None
    if owner is not None and not isinstance(owner, str):
        logger.warning("Session %s... records a non-string owner (%s)", session_id[:8], type(owner).__name__)
        raise deny_unreadable_owner(session_id, username)
    return owner


async def unowned_access(session_id: str, user_data: Dict, request: Request) -> Dict | None:
    """#20025: an existing session with no owner is a defect, and nobody claims it: admins may act, others get a 404.

    No session at all: a read gets the same 404, and None lets a write create it, which is how a new
    id gets its owner. Not knowing which of the two this is denies, as an unknown owner does (#14033).
    """
    from chat_history.session_file import session_file_exists  # noqa: PLC0415
    from utils.chat_utils import get_chat_history_manager  # noqa: PLC0415

    username = user_data.get("username")
    try:
        exists = await session_file_exists(get_chat_history_manager(request), session_id)
    except Exception as exc:
        logger.warning("Could not tell whether session %s... exists: %s", session_id[:8], type(exc).__name__)
        raise deny_unreadable_owner(session_id, username) from None
    if not exists and request.method not in ("GET", "HEAD"):
        return None
    if exists:
        logger.error("Session %s... has no owner: %s by %s", session_id[:8], request.method, username)
    if is_admin_role(user_data.get("role")):
        return {"authorized": True, "user_data": user_data, "reason": "admin_unowned_access"}
    raise HTTPException(status_code=404, detail="Chat session not found")


async def _strict_owner_check(session_id: str, user_data: Dict, request: Request) -> Dict:
    """Admin passes; otherwise the recorded owner must be the caller. Unowned goes to unowned_access."""
    username = user_data.get("username")
    owner = await read_owner(session_id, request, username)
    if owner is None:
        if (decided := await unowned_access(session_id, user_data, request)) is not None:
            return decided
        logger.info("Session %s... has no owner - allowing access (legacy session)", session_id[:8])
        return {"authorized": True, "user_data": user_data, "reason": "legacy_unowned"}
    if owner != username:
        logger.warning("Access denied: %s wanted session %s... owned by %s", username, session_id[:8], owner)
        raise NotSessionOwner()
    return {"authorized": True, "user_data": user_data, "reason": "owner_match"}


async def validate_strict(session_id: str, user_data: Dict, request: Request) -> Dict:
    """The STRICT posture. Always enforces; reads no flag, grants nothing by share or org."""
    try:
        if not user_data.get("role"):
            raise HTTPException(status_code=403, detail="User role not assigned - access denied")
        if is_admin_role(user_data.get("role")):
            return {"authorized": True, "user_data": user_data, "reason": "admin"}
        return await _strict_owner_check(session_id, user_data, request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Session ownership validation error: %s", e)
        raise_internal_error("Failed to validate session ownership")
