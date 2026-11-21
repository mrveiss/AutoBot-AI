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
import time
import uuid
from typing import Any, Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.leader_lease import LeaderLease, worker_identity
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import MS_PER_SECOND

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
# Seconds the lock lives without a renewal (#21456). The holder renews it every ``_HOLD_INTERVAL`` seconds, so it
# lapses only when its holder stops renewing; every other started worker contests it at the same cadence.
_ROUTER_LOCK_TTL = env_int_clamped("AUTOBOT_LLC_NOTIFICATION_ROUTER_LOCK_TTL_SECONDS", 30, min_v=3, max_v=3600)
_ROUTER_LOCK_TTL_MS = _ROUTER_LOCK_TTL * MS_PER_SECOND  # the lease takes milliseconds
_ATTEMPTS_PER_TTL = 3  # hold attempts that fit in one TTL, so one failed attempt leaves two retries
_HOLD_INTERVAL = _ROUTER_LOCK_TTL / _ATTEMPTS_PER_TTL


async def _main_redis(**kwargs: Any) -> Any:
    """The Redis client of the lock; looked up per call so the module's getter can be swapped."""
    return await get_async_redis_client(**kwargs)


class LLCNotificationRouter:
    """Subscribes to llc:* Redis pub/sub and fans out events to WebSocket clients.

    Only the worker holding the single-instance lock routes (GH#8547). Every started worker runs a hold loop for
    its lifetime: the holder renews the lock, any other worker (or one that lost it) contests it, and routing
    runs exactly while the lock is held (#21456).

    Lifecycle:
      await router.start()   # called from lifespan
      await router.stop()    # called from shutdown
    """

    def __init__(self, publisher: Optional[LLCWebSocketPublisher] = None) -> None:
        self._publisher = publisher or LLCWebSocketPublisher()
        self._task: Optional[asyncio.Task] = None  # the routing task, alive only while the lock is held
        self._hold_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._lease = LeaderLease(
            _ROUTER_LOCK_KEY,
            database="main",
            ttl_ms=_ROUTER_LOCK_TTL_MS,
            worker_id=worker_identity(unique=True),
            label="LLC notification router",
            client_factory=_main_redis,
        )
        self._last_held = 0.0  # time.monotonic() taken BEFORE the last call that confirmed the lock

    async def start(self) -> None:
        if self._hold_task and not self._hold_task.done():
            return
        self._stop_event.clear()
        await self._hold_step()
        self._hold_task = asyncio.create_task(self._hold_loop(), name="llc-notification-router-hold")
        logger.info("LLC notification router started")

    async def stop(self) -> None:
        self._stop_event.set()
        await self._cancel_task(self._hold_task)
        self._hold_task = None
        await self._stop_routing()
        await self._lease.release()  # deletes the key only while it still holds this instance's token
        logger.info("LLC notification router stopped")

    @staticmethod
    async def _cancel_task(task: Optional[asyncio.Task]) -> None:
        if task is None:
            return
        task.cancel()
        # ``asyncio.wait`` never raises the task's own cancellation into the caller, so a cancellation aimed at
        # the caller (``stop()`` ending the hold task while it stops routing) is not swallowed here.
        await asyncio.wait([task])
        if not task.cancelled():
            task.exception()  # mark it retrieved

    async def _hold_loop(self) -> None:
        while True:
            await asyncio.sleep(_HOLD_INTERVAL)
            try:
                await self._hold_step()
            except Exception:
                logger.warning("LLC notification router: hold step failed, retrying", exc_info=True)

    async def _hold_step(self) -> None:
        """Take or renew the lock once (owner-checked), then make routing follow the answer.

        Held: route. Another worker's, or gone: stop routing and contest it on the next step. No answer
        (error, timeout, no Redis): keep the current state until a whole TTL passes without a confirmation, since
        the key has expired on the server by then; never route without having held the lock.
        """
        before = time.monotonic()  # the lease can only be shorter than Redis's, never longer
        try:
            held = await asyncio.wait_for(self._lease.hold_or_refresh(), timeout=_HOLD_INTERVAL)
        except Exception:
            logger.warning("LLC notification router: lock check failed, retrying", exc_info=True)
            held = None
        if held:
            self._last_held = before
            self._start_routing()
        elif held is False or time.monotonic() - self._last_held >= _ROUTER_LOCK_TTL:
            await self._stop_routing()

    def _start_routing(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="llc-notification-router")
            logger.info("LLC notification router: lock held, routing")

    async def _stop_routing(self) -> None:
        if self._task is not None and not self._task.done():
            logger.warning("LLC notification router: lock not held, stopping routing")
            await self._cancel_task(self._task)

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
            # Each step bounded and in its own try: a hung socket must not hold up the hold loop (it awaits this
            # when it stops routing), and a failed unsubscribe must not skip closing the connection.
            for close in (pubsub.punsubscribe, pubsub.aclose):
                try:
                    await asyncio.wait_for(close(), timeout=_HOLD_INTERVAL)
                except Exception:
                    logger.warning("LLC router: pubsub cleanup failed or timed out", exc_info=True)

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
