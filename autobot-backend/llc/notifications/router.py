# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC notification router (GH#8255).

Subscribes to llc:* Redis pub/sub patterns and routes each event to the
correct WebSocket clients filtered by company_id.

Watched patterns:
  llc:company:*   — company-level lifecycle events
  llc:budget:*    — budget_warning_80, budget_warning_95, budget_exhausted
  llc:approval:*  — approval_created, approval_resolved
  llc:sprint:*    — sprint_closed, sprint_started
  llc:agent:*     — agent_paused, agent_resumed, heartbeat_ok, heartbeat_missed
  llc:notifications:{company_id} — budget watchdog and handoff producers; the
                    company id is carried by the channel name, not the payload
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import time
import uuid
from typing import Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value, expire_if_value

from .publisher import LLCEvent, LLCWebSocketPublisher

logger = get_logger(__name__)

_PATTERNS = [
    "llc:company:*",
    "llc:budget:*",
    "llc:approval:*",
    "llc:sprint:*",
    "llc:agent:*",
    "llc:notifications:*",
]

_NOTIFICATIONS_PREFIX = "llc:notifications:"
_ENVELOPE_KEYS = frozenset({"event_type", "company_id", "entity_type", "entity_id", "payload", "actor_id"})


def _channel_company_id(channel: object) -> Optional[str]:
    """Return the canonical company UUID of an ``llc:notifications:{id}`` channel.

    Exactly one segment must follow the prefix and it must parse as a UUID (the
    Company OS company id format); anything else (empty, ``a:b``, non-UUID) is
    None.
    """
    if isinstance(channel, bytes):
        channel = channel.decode("utf-8", errors="replace")
    if not isinstance(channel, str) or not channel.startswith(_NOTIFICATIONS_PREFIX):
        return None
    try:
        return str(uuid.UUID(channel[len(_NOTIFICATIONS_PREFIX) :]))
    except ValueError:
        return None


def _is_notifications_channel(channel: object) -> bool:
    if isinstance(channel, bytes):
        channel = channel.decode("utf-8", errors="replace")
    return isinstance(channel, str) and channel.startswith(_NOTIFICATIONS_PREFIX)


def _resolve_company_id(channel: object, data: dict) -> Optional[str]:
    """Company to route to. Notifications channels trust ONLY the channel name
    (tenant isolation); the other watched patterns carry it in the payload."""
    if _is_notifications_channel(channel):
        return _channel_company_id(channel)
    return data.get("company_id")


def _event_payload(data: dict) -> dict:
    """Nested ``payload`` if it is a dict, else the producer's flat extra fields.

    ``company_id`` is an envelope key, so it is never part of the flat payload
    (including when ``payload`` is a non-dict); on notifications channels the
    payload's company_id is ignored in favour of the channel's.
    """
    nested = data.get("payload")
    if isinstance(nested, dict):
        return nested
    return {k: v for k, v in data.items() if k not in _ENVELOPE_KEYS}


_RECONNECT_DELAY = 5  # seconds between reconnect attempts

_ROUTER_LOCK_KEY = "llc:notification_router:leader"
# Seconds the lock lives without a renewal (#21456). The running router renews it every
# ``_RENEW_INTERVAL`` seconds, so it lapses only when its holder stops renewing.
_ROUTER_LOCK_TTL = env_int_clamped("AUTOBOT_LLC_NOTIFICATION_ROUTER_LOCK_TTL_SECONDS", 30, min_v=3, max_v=3600)
_ROUTER_LOCK_TTL_MS = _ROUTER_LOCK_TTL * 1000  # expire_if_value takes milliseconds
_RENEWALS_PER_TTL = 3  # renew attempts that fit in one TTL, so one failed attempt leaves two retries
_RENEW_INTERVAL = _ROUTER_LOCK_TTL / _RENEWALS_PER_TTL


def _new_lock_token() -> str:
    """A value naming ONE router instance: host, process and a random suffix (the lease-holder shape)."""
    return "%s-%d:%s" % (socket.gethostname(), os.getpid(), uuid.uuid4().hex[:8])


class LLCNotificationRouter:
    """Subscribes to llc:* Redis pub/sub and fans out events to WebSocket clients.

    Lifecycle:
      await router.start()   # called from lifespan
      await router.stop()    # called from shutdown
    """

    def __init__(self, publisher: Optional[LLCWebSocketPublisher] = None) -> None:
        self._publisher = publisher or LLCWebSocketPublisher()
        self._task: Optional[asyncio.Task] = None
        self._renew_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._token = _new_lock_token()
        self._holds_lock = False
        self._last_renewed = 0.0  # time.monotonic() of the last acquire or successful renew

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        # Acquire a distributed lock before subscribing so only one uvicorn
        # worker runs the router, preventing 4x duplicate events (GH#8547).
        if not await self._acquire_lock():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="llc-notification-router")
        if self._holds_lock:
            self._renew_task = asyncio.create_task(self._renew_loop(), name="llc-notification-router-renew")
        logger.info("LLC notification router started")

    async def stop(self) -> None:
        self._stop_event.set()
        await self._cancel_task(self._renew_task)
        self._renew_task = None
        await self._cancel_task(self._task)
        await self._release_lock()
        logger.info("LLC notification router stopped")

    @staticmethod
    async def _cancel_task(task: Optional[asyncio.Task]) -> None:
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _acquire_lock(self) -> bool:
        """True when this instance may route: it took the lock, or the lock could not be consulted.

        False only when another worker holds the lock. With no Redis, or on a Redis error, the router
        starts unlocked (as before) and holds nothing, so it renews and releases nothing.
        """
        try:
            redis = await get_async_redis_client(database="main")
            if redis is None:
                return True
            if not await redis.set(_ROUTER_LOCK_KEY, self._token, nx=True, ex=_ROUTER_LOCK_TTL):
                logger.info("LLC notification router: lock held by another worker, skipping")
                return False
            self._holds_lock = True
            self._last_renewed = time.monotonic()
        except Exception as exc:
            logger.warning("LLC notification router: lock check failed (%s), starting anyway", exc)
        return True

    async def _release_lock(self) -> None:
        """Delete the lock only while it still holds this instance's token (compare-and-delete).

        A Redis failure leaves the lock to its TTL; it is logged, never raised.
        """
        if not self._holds_lock:
            return
        self._holds_lock = False
        try:
            redis = await get_async_redis_client(database="main")
            if redis is not None:
                await delete_if_value(redis, _ROUTER_LOCK_KEY, self._token)
        except Exception:
            logger.warning(
                "LLC notification router: lock release failed, leaving it to expire in <=%ds",
                _ROUTER_LOCK_TTL,
                exc_info=True,
            )

    async def _renew_step(self) -> bool:
        """One owner-checked renewal; False once the lock is lost.

        Lost means the key is gone or holds another token, or no renewal has succeeded for a whole TTL (a
        Redis error is retried next tick until then: past the TTL the key has expired on the server anyway).
        """
        try:
            redis = await get_async_redis_client(database="main")
            if redis is None:
                raise RuntimeError("Redis unavailable")
            held = await expire_if_value(redis, _ROUTER_LOCK_KEY, self._token, _ROUTER_LOCK_TTL_MS)
        except Exception:
            logger.warning("LLC notification router: lock renewal failed, retrying", exc_info=True)
            return time.monotonic() - self._last_renewed < _ROUTER_LOCK_TTL
        if held:
            self._last_renewed = time.monotonic()
        return held

    async def _renew_loop(self) -> None:
        while True:
            await asyncio.sleep(_RENEW_INTERVAL)
            if not await self._renew_step():
                self._yield_to_other_router()
                return

    def _yield_to_other_router(self) -> None:
        """Stop routing after the lock was lost, without deleting the key (it is not ours any more)."""
        logger.error("LLC notification router: lock lost to another holder or expired, stopping routing")
        self._holds_lock = False
        self._stop_event.set()
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._subscribe_loop()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("LLC router disconnected (%s), reconnecting in %ds", exc, _RECONNECT_DELAY)
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=_RECONNECT_DELAY)
                except asyncio.TimeoutError:
                    pass

    async def _subscribe_loop(self) -> None:
        redis = await get_async_redis_client(database="main")
        if redis is None:
            raise RuntimeError("Redis unavailable")

        pubsub = redis.pubsub()
        try:
            for pattern in _PATTERNS:
                await pubsub.psubscribe(pattern)
            logger.info("LLC router subscribed to %d patterns", len(_PATTERNS))

            async for message in pubsub.listen():
                if self._stop_event.is_set():
                    break
                if message["type"] not in ("pmessage", "message"):
                    continue
                await self._dispatch(message)
        finally:
            try:
                await pubsub.punsubscribe()
                await pubsub.aclose()
            except Exception:
                pass

    async def _dispatch(self, message: dict) -> None:
        raw = message.get("data")
        if not raw:
            return
        try:
            data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            logger.debug("LLC router: unparseable message on %s", message.get("channel"))
            return

        if not isinstance(data, dict):
            return

        company_id = _resolve_company_id(message.get("channel"), data)
        if not company_id:
            logger.warning(
                "LLC router: dropping %s event on %s — no company_id derivable",
                data.get("event_type", ""),
                message.get("channel"),
            )
            return

        event = LLCEvent(
            company_id=company_id,
            event_type=data.get("event_type", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=str(data.get("entity_id", "")),
            payload=_event_payload(data),
            actor_id=data.get("actor_id"),
        )
        await self._publisher.publish(
            company_id=event.company_id,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=event.payload,
            actor_id=event.actor_id,
        )


_router_instance: Optional[LLCNotificationRouter] = None


def get_llc_notification_router() -> LLCNotificationRouter:
    """Return the process-local router singleton.

    The router acquires a Redis distributed lock on start() so only one
    uvicorn worker actually subscribes to the pub/sub patterns, preventing
    4× duplicate events across workers (GH#8547).
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = LLCNotificationRouter()
    return _router_instance
