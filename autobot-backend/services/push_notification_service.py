# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Web push notification service: VAPID config, dispatch helper, Celery hook (GH#4459).

VAPID keys are loaded from env vars VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY.
Generate a new pair once with ``generate_vapid_keys()`` and persist the output
to your .env file.
"""

import asyncio
import functools
import json
import os
import threading
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.prometheus_metrics import get_metrics_manager

logger = get_logger(__name__)
metrics = get_metrics_manager()

# Module-level constants resolved from env vars (CLAUDE.md TTL pattern / #6743).
_VAPID_PUBLIC_KEY: str = os.environ.get("VAPID_PUBLIC_KEY", "")
_VAPID_PRIVATE_KEY: str = os.environ.get("VAPID_PRIVATE_KEY", "")
_VAPID_CLAIMS_SUB: str = os.environ.get("VAPID_CLAIMS_SUB", "mailto:admin@autobot.local")
_PUSH_NOTIFICATION_TTL: int = int(os.environ.get("AUTOBOT_PUSH_NOTIFICATION_TTL", "86400"))
logger.debug("Push notification TTL: %ds (AUTOBOT_PUSH_NOTIFICATION_TTL)", _PUSH_NOTIFICATION_TTL)


def generate_vapid_keys() -> dict:
    """Generate a new VAPID key pair and return {public_key, private_key}.

    Run once; persist both values to .env as VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY.

    GH#4459: py_vapid API uses save_key/save_public_key methods, not direct attributes.
    """
    try:
        import tempfile

        from py_vapid import Vapid01 as Vapid
    except ImportError as exc:
        raise RuntimeError("pywebpush not installed — run: pip install pywebpush") from exc

    v = Vapid()
    v.generate_keys()

    # Export keys via temp files (py_vapid API requires file paths)
    with (
        tempfile.NamedTemporaryFile(mode="r", delete=True, suffix="_private.pem") as priv_f,
        tempfile.NamedTemporaryFile(mode="r", delete=True, suffix="_public.pem") as pub_f,
    ):
        v.save_key(priv_f.name)
        v.save_public_key(pub_f.name)
        private_key = priv_f.read().strip()
        public_key = pub_f.read().strip()

    return {
        "public_key": public_key,
        "private_key": private_key,
    }


def get_vapid_public_key() -> Optional[str]:
    """Return the configured VAPID public key, or None if not set."""
    return _VAPID_PUBLIC_KEY or None


async def send_push_notification(
    user_id: str,
    title: str,
    body: str,
    url: str = "/",
    *,
    ttl: int = _PUSH_NOTIFICATION_TTL,
) -> int:
    """Send push notifications to all registered endpoints for user_id.

    Sends to both web push subscriptions and paired mobile devices.
    Returns the total number of endpoints that were successfully dispatched to.
    Silently skips (and removes stale) subscriptions that return 410 Gone.
    """
    web_count = await _send_web_push(user_id, title, body, url, ttl)
    mobile_count = await _send_mobile_push(user_id, title, body, url)
    return web_count + mobile_count


async def _send_web_push(
    user_id: str,
    title: str,
    body: str,
    url: str,
    ttl: int,
) -> int:
    """Send web push notifications to browser subscriptions."""
    if not _VAPID_PUBLIC_KEY or not _VAPID_PRIVATE_KEY:
        logger.debug("VAPID keys not configured — web push skipped for user %s", user_id)
        return 0

    try:
        from pywebpush import WebPusher, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed — web push skipped for user %s", user_id)
        return 0

    subscriptions = await _get_subscriptions(user_id)
    if not subscriptions:
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
    claims = {"sub": _VAPID_CLAIMS_SUB}
    dispatched = 0
    stale_endpoints = []

    for sub in subscriptions:
        try:
            pusher = WebPusher(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                }
            )
            response = await asyncio.to_thread(
                functools.partial(
                    pusher.send,
                    data=payload.encode("utf-8"),
                    vapid_private_key=_VAPID_PRIVATE_KEY,
                    vapid_claims=claims,
                    ttl=ttl,
                    content_encoding="aes128gcm",
                )
            )
            if response.status_code == 410:
                stale_endpoints.append(sub["endpoint"])
            elif 200 <= response.status_code < 300:
                dispatched += 1
            else:
                logger.warning(
                    "Push delivery failed for user %s: HTTP %d",
                    user_id,
                    response.status_code,
                )
        except WebPushException as exc:
            logger.warning("WebPushException for user %s endpoint: %s", user_id, exc)
        except Exception:
            logger.exception("Unexpected error sending push for user %s", user_id)

    if stale_endpoints:
        await _remove_stale_subscriptions(stale_endpoints)

    return dispatched


async def _get_subscriptions(user_id: str) -> list[dict]:
    """Fetch all push subscriptions for user_id from the database."""
    try:
        from sqlalchemy import select

        from models.push_subscription import PushSubscription
        from user_management.database import get_async_session_factory

        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id))
            rows = result.scalars().all()
            return [{"endpoint": r.endpoint, "p256dh": r.p256dh, "auth": r.auth} for r in rows]
    except Exception:
        logger.exception("Failed to load push subscriptions for user %s", user_id)
        return []


async def _remove_stale_subscriptions(endpoints: list[str]) -> None:
    """Remove push subscriptions with 410-Gone endpoints."""
    try:
        from sqlalchemy import delete

        from models.push_subscription import PushSubscription
        from user_management.database import get_async_session_factory

        factory = get_async_session_factory()
        async with factory() as session:
            await session.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(endpoints)))
            await session.commit()
            logger.info("Removed %d stale push subscription(s)", len(endpoints))
    except Exception:
        logger.exception("Failed to remove stale push subscriptions")


async def _get_mobile_devices(user_id: str) -> list[dict]:
    """Fetch all paired mobile devices for user_id from the database."""
    try:
        from datetime import timedelta

        from sqlalchemy import select

        from models.mobile_device import MobileDevice
        from user_management.database import get_async_session_factory

        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(select(MobileDevice).where(MobileDevice.user_id == user_id))
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


async def _send_mobile_push(
    user_id: str,
    title: str,
    body: str,
    url: str,
) -> int:
    """Send push notifications to paired mobile devices (APNs/FCM).

    TODO(GH#4463): Implement actual APNs and FCM delivery.
    Currently logs what would be sent; add apns2 and firebase-admin
    dependencies and implement platform-specific dispatch.
    """
    devices = await _get_mobile_devices(user_id)
    if not devices:
        return 0

    dispatched = 0
    for device in devices:
        platform = device["platform"]

        if platform == "ios":
            # TODO: Implement APNs delivery with apns2 library
            logger.info(
                "[STUB] Would send APNs notification to device %s: title=%s, body=%s",
                device["id"],
                title,
                body,
            )
            dispatched += 1
            # GH#4463: Record successful push notification (stub)
            metrics.record_device_push_sent("ios", "success")
        elif platform == "android":
            # TODO: Implement FCM delivery with firebase-admin library
            logger.info(
                "[STUB] Would send FCM notification to device %s: title=%s, body=%s",
                device["id"],
                title,
                body,
            )
            dispatched += 1
            # GH#4463: Record successful push notification (stub)
            metrics.record_device_push_sent("android", "success")
        elif platform == "pwa":
            # PWA uses web push — already handled by _send_web_push
            logger.debug("PWA device %s uses web push, skipping mobile push", device["id"])
        else:
            logger.warning("Unknown platform %s for device %s", platform, device["id"])
            # GH#4463: Record failed push for unknown platform
            metrics.record_device_push_sent(platform, "failure")

    return dispatched


def register_celery_task_success_hook() -> None:
    """Connect a Celery task_success signal that notifies users on completion.

    Call once at application startup.  Only fires for tasks that include
    ``user_id`` in their keyword arguments.
    """
    try:
        from celery.signals import task_success
    except ImportError:
        return

    @task_success.connect
    def _on_task_success(sender=None, result=None, **kwargs):
        task_kwargs = kwargs.get("kwargs") or {}
        user_id = task_kwargs.get("user_id")
        if not user_id:
            return

        task_name = getattr(sender, "name", str(sender))
        # GH#9091: asyncio.run() inside a Celery signal handler raises
        # RuntimeError when a loop is already running (gevent/eventlet pools).
        # Run in a daemon thread so each call owns a fresh event loop regardless
        # of the Celery worker pool type.
        _uid = str(user_id)
        _name = task_name

        def _dispatch() -> None:
            try:
                asyncio.run(
                    send_push_notification(
                        user_id=_uid,
                        title="Task complete",
                        body=f"{_name} finished successfully.",
                        url="/",
                    )
                )
            except Exception:
                logger.debug(
                    "Push notification dispatch failed after task %s",
                    _name,
                    exc_info=True,
                )

        threading.Thread(target=_dispatch, daemon=True).start()
