# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

import json
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select

from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.enums import LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..services.run_checkouts import ReleasedCheckout, ReleaseWhy, drop_released_fences, release_checkouts_for_run
from .base import PollLoopScheduler

logger = get_logger(__name__)

_CHECKPOINT_KEY_PREFIX = "llc:session:checkpoint:"
_SCHEDULE_KEY = "llc:heartbeat:schedule"

#: The lease that elects the one backend worker allowed to run startup recovery.
RECOVERY_LEASE_KEY = "llc:session_recovery:leader"

#: Why a run interrupted at startup gives back its checkouts: the system, on a restart that ended the run.
_RECOVERY_RELEASE = ReleaseWhy(reason=LLCRunStatus.INTERRUPTED.value, source="session_checkpointer")


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


class SessionCheckpointer(PollLoopScheduler):
    """Periodic checkpointer that writes session state to Redis for crash recovery."""

    _task_name = "llc-session-checkpointer"

    def __init__(self, poll_interval: int = LLC_CHECKPOINT_INTERVAL_SECONDS) -> None:
        super().__init__(poll_interval)

    def start(self) -> None:
        """Start the background polling loop."""
        if super().start():
            logger.info("SessionCheckpointer started (poll interval: %ds)", self._poll_interval)

    async def _tick(self) -> None:
        await self._check_once()

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


def recovery_lease() -> LeaderLease:
    """The lease that lets one worker run startup recovery.

    The backend is started with several uvicorn workers (``--workers`` in the backend service unit), and each
    runs its lifespan startup. Recovery interrupts every ``running`` run and now clears its checkouts, so two
    workers racing over it would double-release, and a worker starting later would take a run another worker
    is serving. As in the system knowledge import, the lease is never released: it expires on its own, so
    workers starting in the same window skip.
    """
    return LeaderLease(key=RECOVERY_LEASE_KEY, label="LLC session recovery")


async def recover_incomplete_runs() -> None:
    """Find ``status='running'`` runs at startup and re-queue them for recovery.

    Idempotent: safe to call multiple times.  Only finds runs with
    ``status='running'`` so already-interrupted runs are skipped on a second
    call. Only the worker holding :func:`recovery_lease` recovers; the others skip.
    """
    if not await recovery_lease().update_leadership():
        logger.info("SessionCheckpointer: recovery lease not acquired (another worker or no Redis), skipping")
        return
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
            released: list[ReleasedCheckout] = []

            for run in runs:
                try:
                    run_id = str(run.id)

                    run.status = LLCRunStatus.INTERRUPTED.value
                    run.finished_at = datetime.now(tz=timezone.utc)
                    session.add(run)

                    released.extend(await release_checkouts_for_run(session, run, _RECOVERY_RELEASE))

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
            else:
                await drop_released_fences(released)  # only once the DB release is durable
    except Exception:
        logger.exception("SessionCheckpointer: recover_incomplete_runs failed (swallowed)")
