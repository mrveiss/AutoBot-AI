# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Workflow Memory — Redis-backed KV store for multi-agent collaboration.

Enables agents working on parallel workflow steps to share findings
through a lightweight Redis hash scoped to the workflow ID.

Usage::

    from autobot_shared.workflow_memory import WorkflowMemory

    memory = WorkflowMemory("wf-abc123")
    await memory.write("step1:findings", json.dumps(results))
    prior = await memory.read("step1:findings")
    await memory.clear()  # Call when workflow completes
"""

import logging
from typing import Dict

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Auto-expire stuck workflows after 1 hour
_DEFAULT_TTL_SECONDS = 3600


class WorkflowMemory:
    """Shared KV memory for agents within a single workflow.

    Storage: Redis hash at ``autobot:workflow:{workflow_id}:memory``
    TTL: 1 hour after last write (auto-expires stuck workflows).

    This is the shared library version backed by an async Redis client.
    It is distinct from the orchestration-local WorkflowMemory
    (``autobot-backend/orchestration/workflow_memory.py``) which uses a
    synchronous client for in-process step coordination.
    """

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        self._key = f"autobot:workflow:{workflow_id}:memory"

    async def write(self, key: str, value: str, agent_id: str = "") -> None:
        """Store a key-value pair in shared workflow memory.

        Args:
            key: Memory key (convention: ``{step_id}:result`` or ``shared:*``).
            value: String value (JSON-encode complex data).
            agent_id: Optional agent identifier for audit logging.
        """
        redis = await get_redis_client(async_client=True, database="main")
        await redis.hset(self._key, key, value)
        await redis.expire(self._key, _DEFAULT_TTL_SECONDS)
        if agent_id:
            logger.debug(
                "WorkflowMemory[%s] agent=%s wrote key=%s",
                self.workflow_id,
                agent_id,
                key,
            )

    async def read(self, key: str) -> str | None:
        """Read a specific key from shared workflow memory.

        Args:
            key: Memory key to read.

        Returns:
            Value string or None if not found.
        """
        redis = await get_redis_client(async_client=True, database="main")
        return await redis.hget(self._key, key)

    async def read_all(self) -> Dict[str, str]:
        """Read all shared memory for this workflow.

        Returns:
            Dict of all key-value pairs.
        """
        redis = await get_redis_client(async_client=True, database="main")
        return await redis.hgetall(self._key)

    async def clear(self) -> None:
        """Clean up workflow memory. Call when workflow completes."""
        redis = await get_redis_client(async_client=True, database="main")
        await redis.delete(self._key)
        logger.debug("WorkflowMemory[%s] cleared", self.workflow_id)
