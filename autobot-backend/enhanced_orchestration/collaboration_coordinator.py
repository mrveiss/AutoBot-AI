# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis pub/sub collaboration coordinator extracted from WorkflowRunner (#6393)."""

import asyncio
import json
from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger("collaboration_coordinator")


class CollaborationCoordinator:
    """Manages real-time Redis pub/sub channels between collaborating agents.

    Extracted from WorkflowRunner (#6393) — owns all Redis lifecycle and
    pub/sub logic so WorkflowRunner remains focused on workflow execution.

    Accept a redis_factory for testability (#6401); defaults to the production
    async client so production callers need no changes.

    Design note (GH #6832): although this module has a single caller (WorkflowRunner),
    the redis_factory injection makes it worth keeping separate — tests can pass a mock
    factory without patching module-level globals. Inline only if a second caller never
    materialises.

    # Intentionally single execution-path caller: WorkflowRunner via COLLABORATIVE strategy deps.
    # A second caller requires a distinct multi-agent Redis coordination scenario (file as discovery if needed).
    """

    def __init__(self, redis_factory: Callable = get_async_redis_client) -> None:
        self._redis_async = None
        self._redis_factory = redis_factory

    async def _ensure_redis(self) -> None:
        if self._redis_async is None:
            self._redis_async = await self._redis_factory()
        if self._redis_async is None:
            raise RuntimeError("Redis unavailable — collaboration channel requires Redis")

    async def coordinate_collaboration(self, collab_channel: str) -> None:
        await self._ensure_redis()
        pubsub = self._redis_async.pubsub()
        await pubsub.subscribe(collab_channel)
        shared_context: Dict[str, Any] = {}
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                except json.JSONDecodeError as e:
                    logger.error("Collaboration message decode error: %s", e)
                    continue
                if data.get("type") == "share_insight":
                    shared_context[f"{data.get('agent')}_insight"] = data.get("insight")
                    await self.broadcast_to_agents(
                        collab_channel,
                        {"type": "context_update", "shared_context": shared_context},
                    )
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(collab_channel)

    async def broadcast_to_agents(self, channel: str, data: Dict[str, Any]) -> None:
        await self._ensure_redis()
        await self._redis_async.publish(channel, json.dumps(data))
