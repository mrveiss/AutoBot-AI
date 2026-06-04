# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mobile Device Pairing API (GH#4463)

Endpoints:
  POST   /api/devices/pair          — complete pairing via QR challenge token
  GET    /api/devices/pair-qr       — get a time-limited QR challenge token
  GET    /api/devices               — list devices for the current user
  DELETE /api/devices/{device_id}   — unpair a device

Device tokens expire after 90 days of inactivity; the GET list endpoint
prunes them automatically.
"""

import secrets
import uuid
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc
from models.mobile_device import DevicePlatform, MobileDevice

logger = get_logger(__name__)
metrics = get_metrics_manager()
router = APIRouter()

# QR challenge TTL — 5 minutes is ample for a human to scan
_QR_CHALLENGE_TTL_SECONDS = 300
_DEVICE_EXPIRY_DAYS = 90
_QR_REDIS_PREFIX = "autobot:mobile_pair_challenge:"


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class QRChallengeResponse(BaseModel):
    challenge_token: str = Field(description="Short-lived token embedded in the QR code")
    expires_in_seconds: int = Field(default=_QR_CHALLENGE_TTL_SECONDS)


class PairDeviceRequest(BaseModel):
    challenge_token: str = Field(description="Token obtained from the QR code")
    device_name: str = Field(min_length=1, max_length=255)
    device_token: str = Field(min_length=1, max_length=512, description="APNs / FCM / web-push token")
    platform: DevicePlatform


class DeviceResponse(BaseModel):
    id: uuid.UUID
    device_name: str
    platform: str
    last_seen_at: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class DeviceListResponse(BaseModel):
    devices: List[DeviceResponse]


class PairSuccessResponse(BaseModel):
    device_id: uuid.UUID
    message: str = "Device paired successfully"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _redis_challenge_key(token: str) -> str:
    return f"{_QR_REDIS_PREFIX}{token}"


def _prune_expired(devices: list[MobileDevice]) -> list[MobileDevice]:
    """Return devices active within the last 90 days."""
    cutoff = now_utc() - timedelta(days=_DEVICE_EXPIRY_DAYS)
    return [d for d in devices if d.last_seen_at is None or d.last_seen_at >= cutoff]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pair-qr", response_model=QRChallengeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pair_qr",
    error_code_prefix="MOBILE_DEVICE",
)
async def get_pair_qr(current_user: dict = Depends(get_current_user)) -> QRChallengeResponse:
    """Generate a time-limited QR challenge token for device pairing.

    The caller should embed `challenge_token` in a QR code displayed on
    the desktop. The mobile app scans it, then calls POST /pair with the
    token and its push credentials.
    """
    user_id: str = str(current_user.get("id") or current_user.get("user_id", ""))
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User identity missing")

    redis = get_redis_client(database="main")
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pairing service temporarily unavailable",
        )

    token = secrets.token_urlsafe(32)
    key = _redis_challenge_key(token)
    # Store user_id so the pair endpoint can bind the device to the right user
    redis.setex(key, _QR_CHALLENGE_TTL_SECONDS, user_id)
    logger.info("QR challenge issued for user %s", user_id)
    return QRChallengeResponse(challenge_token=token)


@router.post("/pair", response_model=PairSuccessResponse, status_code=status.HTTP_201_CREATED)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="pair_device",
    error_code_prefix="MOBILE_DEVICE",
)
async def pair_device(
    body: PairDeviceRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PairSuccessResponse:
    """Complete device pairing using a QR challenge token.

    The mobile app presents this endpoint — no user session required as
    authentication is delegated to the challenge token which was bound to
    a user_id at QR-generation time.
    """
    redis = get_redis_client(database="main")
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pairing service temporarily unavailable",
        )

    key = _redis_challenge_key(body.challenge_token)
    raw = redis.get(key)
    if raw is None:
        # GH#4463: Record expired/invalid pairing attempts
        metrics.record_device_pairing_attempt("expired")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge token expired or invalid",
        )

    user_id = raw.decode() if isinstance(raw, bytes) else raw
    # Consume the token — one-time use
    redis.delete(key)

    device = MobileDevice(
        user_id=user_id,
        device_name=body.device_name,
        device_token=body.device_token,
        platform=body.platform.value,
        last_seen_at=now_utc(),
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)
    logger.info("Mobile device %s paired for user %s (platform=%s)", device.id, user_id, body.platform)
    # GH#4463: Record successful pairing attempt
    metrics.record_device_pairing_attempt("success")
    return PairSuccessResponse(device_id=device.id)


@router.get("", response_model=DeviceListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_devices",
    error_code_prefix="MOBILE_DEVICE",
)
async def list_devices(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DeviceListResponse:
    """List active paired devices for the current user.

    Devices inactive for more than 90 days are pruned from the DB on each
    call so storage stays clean without a separate background job.
    """
    user_id: str = str(current_user.get("id") or current_user.get("user_id", ""))

    result = await session.execute(select(MobileDevice).where(MobileDevice.user_id == user_id))
    devices = list(result.scalars().all())

    active = _prune_expired(devices)
    expired_ids = {d.id for d in devices} - {d.id for d in active}
    if expired_ids:
        await session.execute(delete(MobileDevice).where(MobileDevice.id.in_(expired_ids)))
        await session.commit()
        logger.info("Pruned %d expired mobile device(s) for user %s", len(expired_ids), user_id)

    return DeviceListResponse(
        devices=[
            DeviceResponse(
                id=d.id,
                device_name=d.device_name,
                platform=d.platform,
                last_seen_at=d.last_seen_at.isoformat() if d.last_seen_at else None,
                created_at=d.created_at.isoformat(),
            )
            for d in active
        ]
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_device",
    error_code_prefix="MOBILE_DEVICE",
)
async def delete_device(
    device_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Unpair and delete a mobile device."""
    user_id: str = str(current_user.get("id") or current_user.get("user_id", ""))

    result = await session.execute(
        select(MobileDevice).where(
            MobileDevice.id == device_id,
            MobileDevice.user_id == user_id,
        )
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    await session.delete(device)
    await session.commit()
    logger.info("Mobile device %s unpaired for user %s", device_id, user_id)
