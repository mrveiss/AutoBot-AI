# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from autobot_shared.redis_client import get_async_redis_client

from .publisher import LLCEvent, LLCWebSocketPublisher

logger = logging.getLogger(__name__)

_PATTERNS = [
    "llc:company:*",
    "llc:budget:*",
    "llc:approval:*",
    "llc:sprint:*",
    "llc:agent:*",
]

_RECONNECT_DELAY = 5  # seconds between reconnect attempts


class LLCNotificationRouter:
    """Subscribes to llc:* Redis pub/sub and fans out events to WebSocket clients.

    Lifecycle:
      await router.start()   # called from lifespan
      await router.stop()    # called from shutdown
    """

    def __init__(self, publisher: Optional[LLCWebSocketPublisher] = None) -> None:
        self._publisher = publisher or LLCWebSocketPublisher()
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="llc-notification-router")
        logger.info("LLC notification router started")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("LLC notification router stopped")

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
        except (json.JSONDecodeError, TypeError):
            logger.debug("LLC router: unparseable message on %s", message.get("channel"))
            return

        if not isinstance(data, dict):
            return

        company_id = data.get("company_id")
        if not company_id:
            return

        event = LLCEvent(
            company_id=company_id,
            event_type=data.get("event_type", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=str(data.get("entity_id", "")),
            payload=data.get("payload", {}),
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
    global _router_instance
    if _router_instance is None:
        _router_instance = LLCNotificationRouter()
    return _router_instance
