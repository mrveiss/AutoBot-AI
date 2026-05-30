# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Web Push Notification API (GH#4459)

Endpoints:
  POST   /api/push/subscribe       — store a browser push subscription
  DELETE /api/push/unsubscribe     — remove a browser push subscription
  GET    /api/push/vapid-public-key — return the VAPID public key for the SW
"""

import asyncio
import ipaddress
import socket
import uuid
from typing import Dict
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from models.push_subscription import PushSubscription
from services.push_notification_service import get_vapid_public_key

logger = get_logger(__name__)
router = APIRouter()


class SubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    # GH#8967: user_id MUST NOT be accepted from request body.
    # Subscriptions are ALWAYS bound to the authenticated user.
    # If user_id is provided, it will be silently ignored (fail-closed).
    user_id: str | None = None

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint_https(cls, v: str) -> str:
        """Reject non-HTTPS endpoints; verify hostname is present.

        GH#9093: DNS resolution (SSRF check) has been moved to the async
        subscribe() handler so it doesn't block the event loop from inside a
        synchronous Pydantic validator.
        """
        try:
            parsed = urlparse(v)
        except Exception as exc:
            raise ValueError(f"Invalid endpoint URL: {exc}") from exc
        if parsed.scheme != "https":
            raise ValueError("Push endpoint must use https:// scheme")
        if not parsed.hostname:
            raise ValueError("Push endpoint must include a valid host")
        return v


class UnsubscribeRequest(BaseModel):
    endpoint: str
    # GH#8967: user_id MUST NOT be accepted from request body.
    # Unsubscribe targets ONLY the authenticated user's subscription.
    user_id: str | None = None


async def _check_endpoint_not_ssrf(hostname: str) -> None:
    """Resolve hostname and reject private/loopback/link-local IPs (SSRF guard).

    GH#9093: runs DNS resolution in a thread pool via asyncio.to_thread so it
    doesn't stall the uvicorn event loop.  Raises HTTPException(422) on failure.
    """
    try:
        addr_infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Push endpoint hostname could not be resolved: {exc}",
        ) from exc
    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Push endpoint resolves to a private/internal address — SSRF rejected",
            )


@router.get("/vapid-public-key", response_model=Dict[str, str])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vapid_public_key",
    error_code_prefix="PUSH",
)
async def vapid_public_key() -> Dict[str, str]:
    """Return the VAPID public key for service-worker registration."""
    key = get_vapid_public_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID keys not configured — set VAPID_PUBLIC_KEY in .env",
        )
    return {"vapidPublicKey": key}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="push_subscribe",
    error_code_prefix="PUSH",
)
async def subscribe(
    body: SubscribeRequest,
    current_user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, str]:
    """Store a browser Web Push subscription for the authenticated user (GH#8967: IDOR fix).

    Security: subscription user_id is ALWAYS bound to the authenticated user.
    Any user_id in the request body is silently ignored (fail-closed design).
    """
    user_id = current_user.get("user_id") or current_user.get("username", "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cannot identify user")

    # GH#9093: async SSRF guard — DNS check moved here from the Pydantic validator.
    hostname = urlparse(body.endpoint).hostname
    await _check_endpoint_not_ssrf(hostname)

    # GH#8967: Reject IDOR attempts by logging and ignoring any user_id in request body.
    if body.user_id and body.user_id != user_id:
        logger.warning(
            "SECURITY: push subscribe IDOR attempt — attacker user_id=%s, authenticated user_id=%s, endpoint=%s",
            body.user_id,
            user_id,
            body.endpoint[:50],
        )

    # Upsert: if endpoint already exists, update keys in place — but only for the owner.
    result = await session.execute(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    existing = result.scalar_one_or_none()

    if existing:
        # GH#8967 / IDOR: reject if a different user owns this endpoint.
        if existing.user_id != str(user_id):
            logger.warning(
                "SECURITY: push subscribe endpoint conflict — requester=%s, owner=%s, endpoint=%s",
                user_id,
                existing.user_id,
                body.endpoint[:50],
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Endpoint is registered to a different user",
            )
        existing.p256dh = body.p256dh
        existing.auth = body.auth
    else:
        session.add(
            PushSubscription(
                id=str(uuid.uuid4()),
                user_id=str(user_id),
                endpoint=body.endpoint,
                p256dh=body.p256dh,
                auth=body.auth,
            )
        )

    await session.commit()
    logger.info("Push subscription saved for user %s", user_id)
    return {"status": "subscribed"}


@router.delete("/unsubscribe")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="push_unsubscribe",
    error_code_prefix="PUSH",
)
async def unsubscribe(
    body: UnsubscribeRequest,
    current_user: Dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Dict[str, str]:
    """Remove a browser Web Push subscription (GH#8967: IDOR fix).

    Security: unsubscribe targets ONLY the authenticated user's subscription.
    Any user_id in the request body is silently ignored (fail-closed design).
    """
    user_id = current_user.get("user_id") or current_user.get("username", "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cannot identify user")

    # GH#8967: Reject IDOR attempts by logging and ignoring any user_id in request body.
    if body.user_id and body.user_id != user_id:
        logger.warning(
            "SECURITY: push unsubscribe IDOR attempt — attacker user_id=%s, authenticated user_id=%s, endpoint=%s",
            body.user_id,
            user_id,
            body.endpoint[:50],
        )

    result = await session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint,
            PushSubscription.user_id == str(user_id),
        )
    )
    await session.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

    logger.info("Push subscription removed for user %s", user_id)
    return {"status": "unsubscribed"}
