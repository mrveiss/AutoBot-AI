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

logger = get_logger(__name__)

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
    """Send a web push notification to all subscriptions for user_id.

    Returns the number of subscriptions that were successfully dispatched to.
    Silently skips (and removes stale) subscriptions that return 410 Gone.
    """
    if not _VAPID_PUBLIC_KEY or not _VAPID_PRIVATE_KEY:
        logger.warning("VAPID keys not configured — push notification skipped for user %s", user_id)
        return 0

    try:
        from pywebpush import WebPusher, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed — push notification skipped for user %s", user_id)
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
                logger.warning("Push delivery failed for user %s: HTTP %d", user_id, response.status_code)
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
                logger.debug("Push notification dispatch failed after task %s", _name, exc_info=True)

        threading.Thread(target=_dispatch, daemon=True).start()
