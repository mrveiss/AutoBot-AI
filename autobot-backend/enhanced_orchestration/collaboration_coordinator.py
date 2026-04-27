# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Redis pub/sub collaboration coordinator extracted from WorkflowRunner (#6393)."""

import json
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger("collaboration_coordinator")


class CollaborationCoordinator:
    """Manages real-time Redis pub/sub channels between collaborating agents.

    Extracted from WorkflowRunner (#6393) — owns all Redis lifecycle and
    pub/sub logic so WorkflowRunner remains focused on workflow execution.
    """

    def __init__(self) -> None:
        self._redis_async = None

    async def _ensure_redis(self) -> None:
        if self._redis_async is None:
            self._redis_async = await get_async_redis_client()
        if self._redis_async is None:
            raise RuntimeError("Redis unavailable — collaboration channel requires Redis")

    async def coordinate_collaboration(self, plan: Any, collab_channel: str) -> None:
        import asyncio
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
            await pubsub.unsubscribe(collab_channel)
            raise

    async def broadcast_to_agents(self, channel: str, data: Dict[str, Any]) -> None:
        await self._ensure_redis()
        await self._redis_async.publish(channel, json.dumps(data))
