# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Auto-subscriber that closes the Phase 3 resume loop (#7431, ADR-006 §Q1).

Long-running asyncio task that subscribes to the ``skill_promoted`` Redis
pub-sub channel (published by SkillRegistry.register via
skills/skill_promotion_publisher.py) and calls
WorkflowRunner.try_resume_blocked_plan(plan_id) for every blocked plan.

End-to-end resume flow:

  bind_skills can't find a skill for task intent T
    → Phase 3 fires in background; pending_skill_id attached, plan→BLOCKED
    → executor refuses BLOCKED plans
  ...time passes; autonomous-skill-development eventually registers a skill...
  → SkillRegistry.register publishes skill_promoted to Redis
  → THIS resumer wakes
  → for each BLOCKED plan in active_workflows:
       → try_resume_blocked_plan: clear pending IDs, re-bind, execute
  → plan unblocks and runs to completion

Failure modes are tolerated:

- Redis unavailable / disabled → resumer never starts; no error.
- Subscriber loop crashes → logged, loop exits gracefully; existing
  blocked plans require manual resume via try_resume_blocked_plan.
- Per-plan resume failure → logged, other plans still attempted.
- Cancellation (clean shutdown) → loop exits without raising.

Lifecycle: ``start()`` is idempotent; ``stop()`` cancels the listener
task. WorkflowRunner is responsible for both calls.
"""

import asyncio
import json
from typing import Any

from autobot_shared.logging_manager import get_logger
from skills.skill_promotion_publisher import CHANNEL_SKILL_PROMOTED

logger = get_logger(__name__)


class BlockedPlanResumer:
    """Subscribe to ``skill_promoted`` and trigger plan resumes.

    Borrows no state from WorkflowRunner beyond the runner reference;
    on each event, iterates the runner's ``active_workflows`` for
    plans in BLOCKED status and calls ``try_resume_blocked_plan``.
    """

    def __init__(self, runner: Any) -> None:
        self._runner = runner
        self._task: asyncio.Task | None = None
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the subscriber loop. Idempotent — second call is no-op."""
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        """Cancel the subscriber loop and wait for it to exit."""
        self._stopping = True
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):
            pass
        self._task = None

    async def _listen_loop(self) -> None:
        """Connect to Redis pub-sub and dispatch events until cancelled."""
        try:
            from autobot_shared.redis_client import get_async_redis_client
        except ImportError:
            logger.debug("redis_client unavailable; resumer disabled")
            return

        try:
            client = await get_async_redis_client(database="main")
        except Exception as exc:
            logger.warning("resumer: redis client unavailable: %s", exc)
            return
        if client is None:
            logger.debug("Redis disabled; resumer not started")
            return

        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(CHANNEL_SKILL_PROMOTED)
            logger.info("blocked-plan resumer subscribed to %s", CHANNEL_SKILL_PROMOTED)
            async for message in pubsub.listen():
                if self._stopping:
                    break
                if message.get("type") != "message":
                    continue
                await self._handle_event(message.get("data"))
        except asyncio.CancelledError:
            logger.debug("resumer loop cancelled")
        except Exception as exc:
            logger.warning("resumer loop ended unexpectedly: %s", exc)
        finally:
            try:
                await pubsub.unsubscribe(CHANNEL_SKILL_PROMOTED)
            except Exception:
                pass
            try:
                if hasattr(pubsub, "aclose"):
                    await pubsub.aclose()
                elif hasattr(pubsub, "close"):
                    close_result = pubsub.close()
                    if asyncio.iscoroutine(close_result):
                        await close_result
            except Exception:
                pass

    async def _handle_event(self, raw_data: Any) -> None:
        """Decode a skill_promoted message and trigger try_resume on every
        blocked plan. Per-plan resume failures are isolated."""
        try:
            payload = self._decode(raw_data)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.debug("resumer: failed to decode event: %s", exc)
            return

        skill_name = payload.get("skill_name") if isinstance(payload, dict) else None
        logger.debug("resumer: skill_promoted received for skill=%s", skill_name)

        # Snapshot blocked plan IDs so concurrent execute_workflow calls
        # can't grow the iteration set mid-loop.
        blocked_plan_ids = [
            pid for pid, plan in self._runner.active_workflows.items() if getattr(plan, "status", None) == "blocked"
        ]
        for plan_id in blocked_plan_ids:
            try:
                result = await self._runner.try_resume_blocked_plan(plan_id)
                if result.get("resumed"):
                    logger.info("resumer: plan %s resumed after skill=%s", plan_id, skill_name)
            except Exception as exc:
                logger.warning("resumer: try_resume failed for %s: %s", plan_id, exc)

    @staticmethod
    def _decode(raw: Any) -> dict:
        """Decode a pub-sub message body to dict. Tolerates bytes or str."""
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise ValueError("non-string message body")
        return json.loads(raw)
