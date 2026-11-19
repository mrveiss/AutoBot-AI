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
  2. Releases every work-item checkout the run made (the DB row and its Redis fence), returning an
     unfinished item to ``ready`` with its assignee
  3. Re-queues agent in ``llc:heartbeat:schedule`` sorted set at score=now
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select

from autobot_shared.env_utils import env_int_clamped
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


#: How many times startup recovery asks for the lease while Redis does not answer, and the pause between asks.
#: The default spans the lease TTL, so a worker that finds Redis down at boot still recovers once it is back.
RECOVERY_LEASE_ATTEMPTS = env_int_clamped("AUTOBOT_LLC_RECOVERY_LEASE_ATTEMPTS", 6, min_v=1, max_v=60)
RECOVERY_LEASE_RETRY_SECONDS = env_int_clamped("AUTOBOT_LLC_RECOVERY_LEASE_RETRY_SECONDS", 5, min_v=1, max_v=60)


def recovery_lease() -> LeaderLease:
    """The lease that lets one worker run startup recovery.

    The backend is started with several uvicorn workers (``--workers`` in the backend service unit), and each
    runs its lifespan startup. Recovery interrupts every ``running`` run and now clears its checkouts, so two
    workers racing over it would double-release, and a worker starting later would take a run another worker
    is serving. As in the system knowledge import, the lease is never released: it expires on its own, so
    workers starting in the same window skip.
    """
    return LeaderLease(key=RECOVERY_LEASE_KEY, label="LLC session recovery")


async def _requeue_agent(redis, agent_id: str, score: float) -> None:  # noqa: ANN001 - a Redis client or None
    """Put the agent on the heartbeat schedule at *score*; best-effort, a failure is logged and swallowed."""
    if redis is None:
        return
    try:
        await redis.zadd(_SCHEDULE_KEY, {agent_id: score})
    except Exception:
        logger.debug("Redis ZADD re-queue failed for agent %s (swallowed)", agent_id)


async def _acquire_recovery_lease() -> bool:
    """True when this worker holds the recovery lease; False when another worker does, or Redis never answered.

    "Another worker holds it" is a definite answer and ends the wait. "Redis did not answer" is not: it is asked
    again, a bounded number of times, so a Redis that is briefly down at boot does not cost the restart its
    recovery. One holder at a time is still the lease's guarantee, so retrying cannot recover concurrently.
    """
    lease = recovery_lease()
    for attempt in range(1, RECOVERY_LEASE_ATTEMPTS + 1):
        try:
            state = await lease.hold_or_refresh()
        except Exception as exc:
            logger.warning("SessionCheckpointer: recovery lease check failed: %s", exc)
            state = None
        if state is not None:
            return state
        if attempt < RECOVERY_LEASE_ATTEMPTS:
            await asyncio.sleep(RECOVERY_LEASE_RETRY_SECONDS)
    logger.error(
        "SessionCheckpointer: recovery lease unavailable after %d attempt(s) (Redis did not answer); "
        "running runs are left to the liveness monitor",
        RECOVERY_LEASE_ATTEMPTS,
    )
    return False


async def _interrupt_run(session, run: LLCHeartbeatRun) -> list[ReleasedCheckout]:  # noqa: ANN001 - AsyncSession
    """Mark *run* interrupted and release every checkout it made, in the caller's (savepoint) transaction."""
    run.status = LLCRunStatus.INTERRUPTED.value
    run.finished_at = datetime.now(tz=timezone.utc)
    session.add(run)
    return await release_checkouts_for_run(session, run, _RECOVERY_RELEASE)


async def _recover_runs(session, runs: list[LLCHeartbeatRun]) -> None:  # noqa: ANN001 - AsyncSession
    """Interrupt each run in its own savepoint, commit, and only then drop the released fences and re-queue.

    A run whose interrupt or release fails rolls back to its savepoint: it stays ``running``, its locks are not
    dropped and its agent is not re-queued. It keeps its agent busy until the liveness monitor times it out,
    which is the backstop.
    """
    redis = await get_async_redis_client()
    now_ts = time.time()
    released: list[ReleasedCheckout] = []
    requeue: list[str] = []
    for run in runs:
        run_id, agent_id = run.id, run.agent_id  # read while loaded: a savepoint rollback expires the run
        try:
            async with session.begin_nested():  # all of a run's release, or none of it
                batch = await _interrupt_run(session, run)
        except Exception:
            # The run stays ``running`` (and its checkouts held), so the next startup recovers it again.
            logger.exception("Recovery failed for run %s — rolled back to its savepoint", run_id)
            continue
        released.extend(batch)
        requeue.append(agent_id)
        logger.info("SessionCheckpointer: recovered run %s for agent %s", run_id, agent_id)
    try:
        await session.commit()
    except Exception:
        logger.exception("SessionCheckpointer: commit failed during recovery (swallowed)")
        await session.rollback()
    else:
        await drop_released_fences(released)  # only once the DB release is durable
        for agent_id in requeue:  # a poller that sees the wake-up must find the item ready
            await _requeue_agent(redis, agent_id, now_ts)


async def recover_incomplete_runs() -> None:
    """Interrupt every ``running`` run at startup, release its checkouts, and re-queue its agent.

    Does: mark each ``running`` run ``interrupted``, release every checkout it made (an unfinished item goes
    back to ``ready`` with its assignee, so the agent is offered it at its next heartbeat) and re-queue the
    agent. After a full restart every in-flight run is dead (its adapter task lived in the worker), so no age
    bound is applied: an idle agent would otherwise wait for the liveness monitor.

    Idempotent: already-interrupted runs are skipped on a second call. Only the worker holding
    :func:`recovery_lease` recovers; the others skip (strictly safer than before, when every worker ran it).

    Rare case, bounded but not closed: a worker that respawns after the lease TTL while another worker still
    executes a run takes that live run too (a run has no owner field). Its item returns to ``ready`` and the
    agent's next run may check it out again. The original executor's later writes are NOT refused when its
    run no longer holds the checkout: the agent API's status move, comment, attachment and work-product
    writes, the heartbeat report, and the service-level release check only the company or the assignee,
    never ``checkout_run_id`` or the fence value. Run ownership is the proper fix (#21440).
    """
    if not await _acquire_recovery_lease():
        logger.info("SessionCheckpointer: recovery lease not acquired (another worker holds it), skipping")
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
            await _recover_runs(session, runs)
    except Exception:
        logger.exception("SessionCheckpointer: recover_incomplete_runs failed (swallowed)")
