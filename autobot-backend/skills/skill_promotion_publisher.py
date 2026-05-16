# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Publisher for the ``skill_promoted`` Redis pub-sub channel (#7431, ADR-006).

When ``SkillRegistry.register()`` adds a new skill to the runtime, this
publisher emits a message on the ``skill_promoted`` channel so any
subscriber (notably ``BlockedPlanResumer``) can attempt to wake plans
that were waiting on a matching capability.

The publish is best-effort and fire-and-forget:

- Sync caller path: ``SkillRegistry.register()`` is sync, so we schedule
  the publish via ``asyncio.create_task`` when an event loop is running.
  When no loop is running (boot-time registration before the runner
  starts), the publish is silently skipped — no subscriber exists yet.

- Network failures are logged at debug level and never propagate.
  Skill registration must NEVER fail because Redis is unavailable.

Channel name and payload shape are stable contract for the resume path:

  channel: ``skill_promoted``
  payload: JSON {
    "event":         "skill_promoted",
    "skill_name":    str,
    "tools":         list[str],   # from manifest.tools
    "promoted_at":   float        # unix timestamp
  }
"""

import asyncio
import json
import time
from typing import List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

CHANNEL_SKILL_PROMOTED = "skill_promoted"


def publish_skill_promoted(skill_name: str, tools: List[str] | None = None) -> None:
    """Schedule a fire-and-forget publish of ``skill_promoted``.

    Safe to call from sync code: when an event loop is running, schedules
    a background task; when not, logs at debug and returns. Never raises.
    """
    if not skill_name:
        return
    payload = {
        "event": "skill_promoted",
        "skill_name": skill_name,
        "tools": list(tools) if tools else [],
        "promoted_at": time.time(),
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("no running event loop; skipping skill_promoted publish for %s", skill_name)
        return
    loop.create_task(_publish_async(payload))


async def _publish_async(payload: dict) -> None:
    """Publish to Redis pub-sub. Errors are logged, never raised."""
    try:
        from autobot_shared.redis_client import get_async_redis_client
    except ImportError:
        logger.debug("redis_client unavailable; skipping skill_promoted publish")
        return
    try:
        client = await get_async_redis_client(database="main")
        if client is None:
            logger.debug("Redis disabled; skipping skill_promoted publish")
            return
        await client.publish(CHANNEL_SKILL_PROMOTED, json.dumps(payload))
        logger.debug(
            "published skill_promoted: skill=%s tools=%s",
            payload["skill_name"],
            payload["tools"],
        )
    except Exception as exc:
        logger.debug("skill_promoted publish failed: %s", exc)
