# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared chat link endpoints (GH#8996).

Public (unauthenticated) routes:
  GET   /chat/shared/{token}         — read a shared conversation (password-protected optional)
  POST  /chat/shared/{token}/access  — unlock a password-protected link

Authenticated (owner-only) routes:
  POST   /chat/sessions/{session_id}/share-link           — create a shared link
  DELETE /chat/sessions/{session_id}/share-link/{token}   — revoke a link
  GET    /chat/sessions/{session_id}/share-links          — list active links for a session

Config:
  AUTOBOT_SHARED_LINK_DEFAULT_TTL    — default TTL in seconds (0 = no expiry, default: 0)
  AUTOBOT_SHARED_LINK_ACCESS_RPM     — max password attempts per minute per IP (default: 10)
  AUTOBOT_SHARED_LINK_ACCESS_RPH     — max password attempts per hour per IP (default: 100)
"""

import os
import secrets
import uuid
from datetime import timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_chat import (
    SharedLinkAccessRequest,
    SharedLinkAdminItem,
    SharedLinkCreateRequest,
    SharedLinkData,
    SharedLinkSessionData,
    SharedMessageItem,
)
from api.user_management.dependencies import get_db_session
from api.voice_bundle_helpers import _require_admin
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.proxy_utils import get_client_ip
from autobot_shared.rate_limiter import RateLimiter
from autobot_shared.time_utils import now_utc
from models.chat_shared_link import ChatSharedLink
from security.session_ownership import SessionOwnershipValidator
from user_management.services.user_service import UserService
from utils.chat_utils import get_chat_history_manager, validate_chat_session_id
from utils.response_helpers import create_success_response

logger = get_logger(__name__)

router = APIRouter(tags=["chat-shared-links"])

_DEFAULT_TTL_ENV = "AUTOBOT_SHARED_LINK_DEFAULT_TTL"
_DEFAULT_TTL_SECONDS: int = int(os.environ.get(_DEFAULT_TTL_ENV, "0"))
if _DEFAULT_TTL_SECONDS > 0:
    logger.info("Shared link default TTL: %ds (from %s)", _DEFAULT_TTL_SECONDS, _DEFAULT_TTL_ENV)
else:
    logger.info("Shared link default TTL: none (links never expire unless requested)")

# Rate limiter for the unauthenticated /access endpoint — brute-force guard (GH#9127).
# Keyed per client IP, sliding-window via Redis.
_ACCESS_RPM: int = int(os.environ.get("AUTOBOT_SHARED_LINK_ACCESS_RPM", "10"))
_ACCESS_RPH: int = int(os.environ.get("AUTOBOT_SHARED_LINK_ACCESS_RPH", "100"))
_access_limiter = RateLimiter(
    scope_prefix="shared_link_access",
    default_tier="anonymous",
    requests_per_minute=_ACCESS_RPM,
    requests_per_hour=_ACCESS_RPH,
)
logger.info(
    "Shared link access rate limit: %d/min %d/hr per IP (AUTOBOT_SHARED_LINK_ACCESS_RPM/RPH)",
    _ACCESS_RPM,
    _ACCESS_RPH,
)

_TOKEN_BYTES = 24  # 32-char URL-safe base64 token


def _generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


# ============================================================
# Authenticated — owner endpoints
# ============================================================


@router.post(
    "/chat/sessions/{session_id}/share-link",
    response_model=Dict[str, Any],
    summary="Create a public shared link for a chat session",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_shared_link",
    error_code_prefix="CHAT_SHARED_LINKS",
)
async def create_shared_link(
    session_id: str,
    body: SharedLinkCreateRequest,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Create a tokenized public link for a chat session (GH#8996)."""
    validate_chat_session_id(session_id)

    from autobot_shared.redis_client import get_redis_client as get_redis_mgr

    redis = await get_redis_mgr(async_client=True, database="main")
    validator = SessionOwnershipValidator(redis)
    user_id = current_user.get("user_id") or current_user.get("username", "")

    owner = await validator.get_session_owner(session_id)
    if owner is None or owner != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the session owner")

    password_hash: str | None = None
    if body.password:
        password_hash = UserService.hash_password(body.password)  # nosec B106

    ttl = body.expires_in_seconds or _DEFAULT_TTL_SECONDS
    expires_at = now_utc() + timedelta(seconds=ttl) if ttl > 0 else None

    link = ChatSharedLink(
        id=uuid.uuid4(),
        session_id=session_id,
        token=_generate_token(),
        password_hash=password_hash,
        expires_at=expires_at,
        created_by=user_id,
        is_active=True,
        created_at=now_utc(),
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    logger.info("Created shared link token=%s session=%s by=%s", link.token[:8], session_id, user_id)

    return create_success_response(
        data=SharedLinkData(
            token=link.token,
            session_id=session_id,
            has_password=link.has_password,
            expires_at=link.expires_at,
            created_at=link.created_at,
        ).model_dump(mode="json"),
        message="Shared link created",
    )


@router.delete(
    "/chat/sessions/{session_id}/share-link/{token}",
    response_model=Dict[str, Any],
    summary="Revoke a shared link",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="revoke_shared_link",
    error_code_prefix="CHAT_SHARED_LINKS",
)
async def revoke_shared_link(
    session_id: str,
    token: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Revoke (deactivate) a shared link (GH#8996)."""
    validate_chat_session_id(session_id)
    user_id = current_user.get("user_id") or current_user.get("username", "")

    result = await db.execute(
        select(ChatSharedLink).where(
            ChatSharedLink.token == token,
            ChatSharedLink.session_id == session_id,
        )
    )
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found")

    if link.created_by != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the link owner")

    link.is_active = False
    await db.commit()

    logger.info("Revoked shared link token=%s session=%s by=%s", token[:8], session_id, user_id)
    return create_success_response(data={"revoked": True}, message="Shared link revoked")


@router.get(
    "/chat/sessions/{session_id}/share-links",
    response_model=Dict[str, Any],
    summary="List active shared links for a session",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_shared_links",
    error_code_prefix="CHAT_SHARED_LINKS",
)
async def list_shared_links(
    session_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """List all active shared links for a session (GH#8996)."""
    validate_chat_session_id(session_id)

    from autobot_shared.redis_client import get_redis_client as get_redis_mgr

    redis = await get_redis_mgr(async_client=True, database="main")
    validator = SessionOwnershipValidator(redis)
    user_id = current_user.get("user_id") or current_user.get("username", "")

    owner = await validator.get_session_owner(session_id)
    if owner is None or owner != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the session owner")

    result = await db.execute(
        select(ChatSharedLink).where(
            ChatSharedLink.session_id == session_id,
            ChatSharedLink.is_active.is_(True),
        )
    )
    links: List[ChatSharedLink] = list(result.scalars().all())

    items = [
        SharedLinkData(
            token=lnk.token,
            session_id=session_id,
            has_password=lnk.has_password,
            expires_at=lnk.expires_at,
            created_at=lnk.created_at,
        ).model_dump(mode="json")
        for lnk in links
        if not lnk.is_expired
    ]

    return create_success_response(data={"links": items, "count": len(items)}, message="Active shared links")


# ============================================================
# Admin — cross-user view of all active links
# ============================================================


@router.get(
    "/chat/shared-links/admin",
    response_model=Dict[str, Any],
    summary="List all active shared links across all users (admin)",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_all_shared_links_admin",
    error_code_prefix="CHAT_SHARED_LINKS",
)
async def list_all_shared_links_admin(
    request: Request,
    admin_user: Dict = Depends(_require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Return every active (non-expired) shared link with its owner (GH#8996, AC4)."""
    result = await db.execute(
        select(ChatSharedLink).where(ChatSharedLink.is_active.is_(True)).order_by(ChatSharedLink.created_at.desc())
    )
    links: List[ChatSharedLink] = list(result.scalars().all())

    items = [
        SharedLinkAdminItem(
            id=str(lnk.id),
            token=lnk.token,
            session_id=lnk.session_id,
            owner=lnk.created_by,
            has_password=lnk.has_password,
            expires_at=lnk.expires_at,
            created_at=lnk.created_at,
        ).model_dump(mode="json")
        for lnk in links
        if not lnk.is_expired
    ]

    return create_success_response(
        data={"links": items, "count": len(items)}, message="All active shared links"
    ).model_dump(mode="json")


# ============================================================
# Public — unauthenticated access
# ============================================================


async def _resolve_link(token: str, db: AsyncSession) -> ChatSharedLink:
    """Fetch and validate a shared link, raising 404/410 on failure."""
    result = await db.execute(
        select(ChatSharedLink).where(
            ChatSharedLink.token == token,
            ChatSharedLink.is_active.is_(True),
        )
    )
    link = result.scalar_one_or_none()

    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared link not found or revoked")

    if link.is_expired:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Shared link has expired")

    return link


@router.get(
    "/chat/shared/{token}",
    response_model=Dict[str, Any],
    summary="Access a shared conversation (public)",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_shared_session",
    error_code_prefix="CHAT_SHARED_LINKS",
)
async def get_shared_session(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Return shared conversation content.  Password-protected links return metadata only (GH#8996)."""
    link = await _resolve_link(token, db)

    if link.has_password:
        return create_success_response(
            data=SharedLinkSessionData(
                session_id=link.session_id,
                title=None,
                messages=[],
                has_password=True,
            ).model_dump(mode="json"),
            message="Password required",
        )

    return await _load_session_data(link, request)


@router.post(
    "/chat/shared/{token}/access",
    response_model=Dict[str, Any],
    summary="Unlock a password-protected shared link",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="access_shared_session",
    error_code_prefix="CHAT_SHARED_LINKS",
)
async def access_shared_session(
    token: str,
    body: SharedLinkAccessRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Verify password and return conversation content (GH#8996, rate-limited GH#9127)."""
    client_ip = get_client_ip(request) or "unknown"
    allowed = await _access_limiter.acquire(client_ip)
    if not allowed:
        retry_after = await _access_limiter.get_retry_after_seconds(client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many access attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    link = await _resolve_link(token, db)

    if link.has_password:
        if not body.password:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Password required")
        if not UserService.verify_password(body.password, link.password_hash):  # type: ignore[arg-type]
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

    return await _load_session_data(link, request)


async def _load_session_data(link: ChatSharedLink, request: Request) -> Dict[str, Any]:
    """Fetch messages for the linked session and build the response."""
    chat_history_manager = get_chat_history_manager(request)
    messages: List[SharedMessageItem] = []

    if chat_history_manager:
        raw = await chat_history_manager.get_session_messages(link.session_id, limit=500)
        messages = [
            SharedMessageItem(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                created_at=m.get("created_at"),
            )
            for m in (raw or [])
            if m.get("role") in {"user", "assistant"}
        ]

    return create_success_response(
        data=SharedLinkSessionData(
            session_id=link.session_id,
            title=None,
            messages=messages,
            has_password=link.has_password,
        ).model_dump(mode="json"),
        message="Shared session retrieved",
    )
