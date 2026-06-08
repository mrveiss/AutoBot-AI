# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pool-change invalidation for shard plans.

Subscribes to ``npu.worker.added`` and ``npu.worker.removed`` events emitted
by ``npu_worker_manager`` and clears every cached shard plan that referenced
the affected worker.

Plan IDs have the form ``{model_id}::{sorted_worker_ids}``.  On a worker
add/remove we do not know which models were planned with that worker, so we
scan all ``npu:pipeline:*`` keys and drop those whose plan_id contains the
worker_id.  This is conservative but safe and the key space is bounded.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from events.bus import get_event_bus
from services.npu_pipeline.plan_cache import _KEY_PREFIX, RedisShardPlanCache

logger = get_logger(__name__)

_REDIS_DATABASE = "main"


class PlanInvalidationHandler:
    """Subscribes to worker lifecycle events and evicts stale plans.

    Usage::

        handler = PlanInvalidationHandler(cache)
        handler.register()          # start listening
        ...
        handler.unregister()        # stop listening
    """

    def __init__(self, cache: RedisShardPlanCache | None = None) -> None:
        self._cache = cache or RedisShardPlanCache()
        self._registered = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register(self) -> None:
        """Subscribe to worker.added and worker.removed events."""
        if self._registered:
            return
        bus = get_event_bus()
        bus.subscribe("npu.worker.added", self._on_worker_changed)
        bus.subscribe("npu.worker.removed", self._on_worker_changed)
        self._registered = True
        logger.info("PlanInvalidationHandler registered")

    def unregister(self) -> None:
        """Unsubscribe from worker events."""
        if not self._registered:
            return
        bus = get_event_bus()
        bus.unsubscribe("npu.worker.added", self._on_worker_changed)
        bus.unsubscribe("npu.worker.removed", self._on_worker_changed)
        self._registered = False
        logger.info("PlanInvalidationHandler unregistered")

    # ------------------------------------------------------------------
    # Event handler
    # ------------------------------------------------------------------

    async def _on_worker_changed(self, event: Dict[str, Any]) -> None:
        """Clear all plans that involve the changed worker."""
        worker_id = event.get("worker_id", "")
        if not worker_id:
            logger.warning("PlanInvalidationHandler: missing worker_id in event %s", event)
            return

        event_type = event.get("event", "unknown")
        logger.info(
            "PlanInvalidationHandler: invalidating plans for worker '%s' (event=%s)",
            worker_id,
            event_type,
        )
        await self._evict_plans_for_worker(worker_id)

    async def _evict_plans_for_worker(self, worker_id: str) -> int:
        """Scan ``npu:pipeline:*`` keys and delete those referencing *worker_id*."""
        try:
            client = await get_async_redis_client(database=_REDIS_DATABASE)
            pattern = f"{_KEY_PREFIX}*"
            keys = await client.keys(pattern)
            if not keys:
                return 0

            to_delete = [k for k in keys if self._plan_involves_worker(k, worker_id)]
            if not to_delete:
                return 0

            count = await client.delete(*to_delete)
            logger.info(
                "PlanInvalidationHandler: deleted %d plan(s) referencing worker '%s'",
                count,
                worker_id,
            )
            return count
        except Exception as exc:
            logger.error(
                "PlanInvalidationHandler: error evicting plans for worker '%s': %s",
                worker_id,
                exc,
            )
            return 0

    @staticmethod
    def _plan_involves_worker(redis_key: bytes | str, worker_id: str) -> bool:
        """Return True when the key's plan_id contains *worker_id*."""
        key_str = redis_key.decode() if isinstance(redis_key, bytes) else redis_key
        # plan_id = everything after the prefix; worker IDs are comma-separated
        plan_id = key_str[len(_KEY_PREFIX) :]
        return worker_id in plan_id


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_handler: PlanInvalidationHandler | None = None
_handler_lock = asyncio.Lock()


async def get_plan_invalidation_handler(
    cache: RedisShardPlanCache | None = None,
) -> PlanInvalidationHandler:
    """Return the singleton handler, registering it if first call."""
    global _handler
    if _handler is None:
        async with _handler_lock:
            if _handler is None:
                _handler = PlanInvalidationHandler(cache)
                _handler.register()
    return _handler
