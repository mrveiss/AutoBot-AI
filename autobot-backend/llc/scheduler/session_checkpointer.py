# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC session checkpointer — periodic checkpoint writes and crash recovery (GH#9026).

Runs every LLC_CHECKPOINT_INTERVAL_SECONDS (default 30). For each running
heartbeat run writes Redis key ``llc:session:checkpoint:{run_id}`` with TTL.

On startup, :func:`recover_incomplete_runs` is called BEFORE the heartbeat
scheduler begins dispatching.  For each ``status='running'`` run it:
  1. Marks run ``interrupted``
  2. Releases ``llc:checkout:{work_item_id}`` lock
  3. Re-queues agent in ``llc:heartbeat:schedule`` sorted set at score=now
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.enums import LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun

logger = logging.getLogger(__name__)

_CHECKPOINT_KEY_PREFIX = "llc:session:checkpoint:"
_CHECKOUT_KEY_PREFIX = "llc:checkout:"
_SCHEDULE_KEY = "llc:heartbeat:schedule"


def _resolve_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value <= 0:
            logger.warning("%s=%d must be positive; using default %d", name, value, default)
            return default
        return value
    except ValueError:
        logger.warning("%s=%r is not an integer; using default %d", name, raw, default)
        return default


LLC_CHECKPOINT_INTERVAL_SECONDS = _resolve_int_env("LLC_CHECKPOINT_INTERVAL_SECONDS", 30)
LLC_CHECKPOINT_TTL_SECONDS = _resolve_int_env("LLC_CHECKPOINT_TTL_SECONDS", 86400)

logger.info(
    "SessionCheckpointer defaults: interval=%ds ttl=%ds",
    LLC_CHECKPOINT_INTERVAL_SECONDS,
    LLC_CHECKPOINT_TTL_SECONDS,
)


class SessionCheckpointer:
    """Periodic checkpointer that writes session state to Redis for crash recovery."""

    def __init__(self, poll_interval: int = LLC_CHECKPOINT_INTERVAL_SECONDS) -> None:
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="llc-session-checkpointer")
        logger.info("SessionCheckpointer started (poll interval: %ds)", self._poll_interval)

    def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("SessionCheckpointer._check_once failed")
            await asyncio.sleep(self._poll_interval)

    async def _check_once(self) -> None:
        """Single scan — write checkpoints for all currently running runs."""
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.status == "running"))
            runs = list(result.scalars().all())
            for run in runs:
                try:
                    await self._write_checkpoint(run)
                except Exception:
                    logger.debug("_write_checkpoint failed for run %s (swallowed)", run.id)

    async def _write_checkpoint(self, run: LLCHeartbeatRun) -> None:
        """Write Redis key ``llc:session:checkpoint:{run_id}`` with JSON payload and TTL."""
        redis = await get_async_redis_client()
        if redis is None:
            return
        payload = json.dumps(
            {
                "run_id": str(run.id),
                "agent_id": run.agent_id,
                "company_id": str(run.company_id),
                "work_item_id": str(run.work_item_id) if run.work_item_id else None,
                "external_run_id": run.external_run_id,
                "context_snapshot": run.context_snapshot,
                "checkpoint_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
        key = f"{_CHECKPOINT_KEY_PREFIX}{run.id}"
        await redis.set(key, payload, ex=LLC_CHECKPOINT_TTL_SECONDS)


async def recover_incomplete_runs() -> None:
    """Find ``status='running'`` runs at startup and re-queue them for recovery.

    Idempotent: safe to call multiple times.  Only finds runs with
    ``status='running'`` so already-interrupted runs are skipped on a second
    call.
    """
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(select(LLCHeartbeatRun).where(LLCHeartbeatRun.status == "running"))
            runs = list(result.scalars().all())

            if not runs:
                logger.info("SessionCheckpointer: no incomplete runs to recover")
                return

            logger.info("SessionCheckpointer: recovering %d incomplete run(s)", len(runs))

            redis = await get_async_redis_client()
            now_ts = time.time()

            for run in runs:
                try:
                    run_id = str(run.id)

                    run.status = LLCRunStatus.INTERRUPTED.value
                    run.finished_at = datetime.now(tz=timezone.utc)
                    session.add(run)

                    if run.work_item_id and redis is not None:
                        try:
                            await redis.delete(f"{_CHECKOUT_KEY_PREFIX}{run.work_item_id}")
                        except Exception:
                            logger.debug("Redis DEL checkout key failed for run %s (swallowed)", run_id)

                    if redis is not None:
                        try:
                            await redis.zadd(_SCHEDULE_KEY, {run.agent_id: now_ts})
                        except Exception:
                            logger.debug("Redis ZADD re-queue failed for agent %s (swallowed)", run.agent_id)

                    logger.info(
                        "SessionCheckpointer: recovered run %s for agent %s",
                        run_id,
                        run.agent_id,
                    )
                except Exception:
                    logger.exception("Recovery failed for run %s (swallowed)", run.id)

            try:
                await session.commit()
            except Exception:
                logger.exception("SessionCheckpointer: commit failed during recovery (swallowed)")
                await session.rollback()
    except Exception:
        logger.exception("SessionCheckpointer: recover_incomplete_runs failed (swallowed)")
