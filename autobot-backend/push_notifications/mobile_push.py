# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Mobile push notification delivery (MVA-2994).

Implements platform-specific push delivery to paired mobile devices:
- iOS: APNs (Apple Push Notification service)
- Android: FCM (Firebase Cloud Messaging)
- PWA: Web Push (handled by push_notification_service)

Integration points:
- Agent workflow completion
- Long-running task completion
- Chat message received (offline)
"""

import asyncio
import os
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

logger = get_logger(__name__)
metrics = get_metrics_manager()

# APNs configuration
_APNS_KEY_ID: str = os.environ.get("APNS_KEY_ID", "")
_APNS_TEAM_ID: str = os.environ.get("APNS_TEAM_ID", "")
_APNS_KEY_PATH: str = os.environ.get("APNS_KEY_PATH", "")
_APNS_USE_SANDBOX: bool = os.environ.get("APNS_USE_SANDBOX", "false").lower() == "true"

# FCM configuration
_FCM_PROJECT_ID: str = os.environ.get("FCM_PROJECT_ID", "")
_FCM_CREDENTIALS_PATH: str = os.environ.get("FCM_CREDENTIALS_PATH", "")


async def send_push_to_user(
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    *,
    device_id: Optional[str] = None,
) -> dict[str, int]:
    """Send push notifications to paired mobile devices for user_id.

    Routes to correct platform (APNs/FCM) based on device platform.
    Returns count of successful deliveries per platform.

    Args:
        user_id: Target user ID
        title: Notification title
        body: Notification body text
        url: Deep link URL (default: "/")
        device_id: Optional device ID to target specific device only

    Returns:
        dict with success counts: {"ios": 0, "android": 0, "failed": 0}

    Handles:
        - Invalid/expired device tokens (removes from DB)
        - Platform-specific token formats
        - Graceful degradation when credentials not configured
    """
    devices = await _get_target_devices(user_id, device_id)
    if not devices:
        logger.debug("No mobile devices found for user %s", user_id)
        return {"ios": 0, "android": 0, "failed": 0}

    results = {"ios": 0, "android": 0, "failed": 0}
    invalid_device_ids = []

    for device in devices:
        platform = device["platform"]
        device_token = device["device_token"]
        dev_id = device["id"]

        try:
            if platform == "ios":
                success = await _send_apns(device_token, title, body, url)
                if success:
                    results["ios"] += 1
                    metrics.record_device_push_sent("ios", "success")
                else:
                    results["failed"] += 1
                    metrics.record_device_push_sent("ios", "failure")
            elif platform == "android":
                success = await _send_fcm(device_token, title, body, url)
                if success:
                    results["android"] += 1
                    metrics.record_device_push_sent("android", "success")
                else:
                    results["failed"] += 1
                    metrics.record_device_push_sent("android", "failure")
            elif platform == "pwa":
                # PWA uses web push — skip here
                logger.debug("PWA device %s uses web push, skipping mobile push", dev_id)
                continue
            else:
                logger.warning("Unknown platform %s for device %s", platform, dev_id)
                metrics.record_device_push_sent(platform, "failure")
                results["failed"] += 1

        except InvalidTokenError:
            logger.warning("Invalid token for device %s (platform: %s) — marking for removal", dev_id, platform)
            invalid_device_ids.append(dev_id)
            results["failed"] += 1
        except Exception:
            logger.exception("Unexpected error sending push to device %s", dev_id)
            results["failed"] += 1

    # Clean up invalid tokens
    if invalid_device_ids:
        await _remove_invalid_devices(invalid_device_ids)

    return results


async def _get_target_devices(user_id: str, device_id: Optional[str] = None) -> list[dict]:
    """Fetch mobile devices for user (or specific device if device_id provided)."""
    try:
        from datetime import timedelta

        from sqlalchemy import select

        from models.mobile_device import MobileDevice
        from user_management.database import get_async_session_factory

        factory = get_async_session_factory()
        async with factory() as session:
            query = select(MobileDevice).where(MobileDevice.user_id == user_id)

            if device_id:
                query = query.where(MobileDevice.id == device_id)

            result = await session.execute(query)
            devices = result.scalars().all()

            # Filter to only active devices (seen within 90 days)
            from autobot_shared.time_utils import now_utc

            cutoff = now_utc() - timedelta(days=90)
            active = [
                {
                    "id": str(d.id),
                    "device_token": d.device_token,  # property auto-decrypts
                    "platform": d.platform,
                }
                for d in devices
                if d.last_seen_at is None or d.last_seen_at >= cutoff
            ]
            return active
    except Exception:
        logger.exception("Failed to load mobile devices for user %s", user_id)
        return []


async def _send_apns(device_token: str, title: str, body: str, url: str) -> bool:
    """Send push notification via APNs (Apple Push Notification service).

    Returns True if successfully sent, False otherwise.
    Raises InvalidTokenError if token is invalid/expired.
    """
    if not _APNS_KEY_ID or not _APNS_TEAM_ID or not _APNS_KEY_PATH:
        logger.warning("APNs credentials not configured — skipping iOS push")
        return False

    try:
        # Import apns2 library (optional dependency)
        from apns2.client import APNsClient
        from apns2.errors import BadDeviceToken, Unregistered
        from apns2.payload import Payload

        # Initialize client (production or sandbox)
        client = APNsClient(
            credentials=_APNS_KEY_PATH,
            use_sandbox=_APNS_USE_SANDBOX,
            team_id=_APNS_TEAM_ID,
            auth_key_id=_APNS_KEY_ID,
        )

        # Build payload
        payload = Payload(
            alert={"title": title, "body": body},
            sound="default",
            badge=1,
            custom={"url": url},
        )

        # Send notification
        response = await asyncio.to_thread(
            client.send_notification,
            device_token,
            payload,
            topic=os.environ.get("APNS_BUNDLE_ID", "ai.autobot.mobile"),
        )

        if response.is_successful:
            logger.info("APNs notification sent successfully to token %s...", device_token[:16])
            return True
        else:
            logger.warning("APNs delivery failed: %s", response.description)
            return False

    except (BadDeviceToken, Unregistered) as exc:
        logger.warning("APNs token invalid or unregistered: %s", exc)
        raise InvalidTokenError(f"APNs token invalid: {exc}") from exc
    except ImportError:
        logger.warning("apns2 library not installed — install with: pip install apns2")
        return False
    except Exception:
        logger.exception("Unexpected error sending APNs notification")
        return False


async def _send_fcm(device_token: str, title: str, body: str, url: str) -> bool:
    """Send push notification via FCM (Firebase Cloud Messaging).

    Returns True if successfully sent, False otherwise.
    Raises InvalidTokenError if token is invalid/expired.
    """
    if not _FCM_PROJECT_ID or not _FCM_CREDENTIALS_PATH:
        logger.warning("FCM credentials not configured — skipping Android push")
        return False

    try:
        # Import firebase_admin library (optional dependency)
        import firebase_admin
        from firebase_admin import credentials, messaging
        from firebase_admin.exceptions import FirebaseError

        # Initialize Firebase app if not already initialized
        try:
            firebase_admin.get_app()
        except ValueError:
            cred = credentials.Certificate(_FCM_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)

        # Build message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data={"url": url},
            token=device_token,
        )

        # Send notification
        response = await asyncio.to_thread(messaging.send, message)
        logger.info("FCM notification sent successfully: %s", response)
        return True

    except FirebaseError as exc:
        error_code = getattr(exc, "code", "")
        if error_code in ("registration-token-not-registered", "invalid-registration-token"):
            logger.warning("FCM token invalid: %s", exc)
            raise InvalidTokenError(f"FCM token invalid: {exc}") from exc
        else:
            logger.warning("FCM delivery failed: %s", exc)
            return False
    except ImportError:
        logger.warning("firebase-admin library not installed — install with: pip install firebase-admin")
        return False
    except Exception:
        logger.exception("Unexpected error sending FCM notification")
        return False


async def _remove_invalid_devices(device_ids: list[str]) -> None:
    """Remove mobile devices with invalid/expired tokens from database."""
    if not device_ids:
        return

    try:
        from sqlalchemy import delete

        from models.mobile_device import MobileDevice
        from user_management.database import get_async_session_factory

        factory = get_async_session_factory()
        async with factory() as session:
            await session.execute(delete(MobileDevice).where(MobileDevice.id.in_(device_ids)))
            await session.commit()
            logger.info("Removed %d invalid mobile device(s)", len(device_ids))
    except Exception:
        logger.exception("Failed to remove invalid mobile devices")


class InvalidTokenError(Exception):
    """Raised when a device token is invalid or expired."""
