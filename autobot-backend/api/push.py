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

import uuid
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
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


class UnsubscribeRequest(BaseModel):
    endpoint: str


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
    """Store a browser Web Push subscription for the authenticated user."""
    user_id = current_user.get("user_id") or current_user.get("username", "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cannot identify user")

    # Upsert: if endpoint already exists, update keys in place.
    result = await session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.p256dh = body.p256dh
        existing.auth = body.auth
        existing.user_id = str(user_id)
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
    """Remove a browser Web Push subscription."""
    user_id = current_user.get("user_id") or current_user.get("username", "")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cannot identify user")

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
