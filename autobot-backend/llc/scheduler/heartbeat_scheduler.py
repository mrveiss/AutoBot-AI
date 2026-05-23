# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""HeartbeatScheduler — Redis sorted-set dispatch engine (GH#8225).

Architecture:
  - On startup: loads all heartbeat-enabled agents from DB, computes next fire
    time via croniter, writes to Redis sorted set ``llc:heartbeat:schedule``
    with score = next-fire epoch (float seconds).
  - Polling loop: every 5s, ``ZRANGEBYSCORE 0 {now}`` to find due agents.
  - For each due agent: creates llc_heartbeat_runs row, dispatches adapter
    task (async, fire-and-forget), advances sorted-set score to next fire.
  - Restart-safe: re-reads DB and re-populates sorted set idempotently.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from croniter import croniter
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.enums import HeartbeatInvocationSource, HeartbeatRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun

logger = logging.getLogger(__name__)

_SCHEDULE_KEY = "llc:heartbeat:schedule"
_POLL_INTERVAL = 5.0  # seconds between sorted-set polls


class HeartbeatScheduler:
    """Cron-driven heartbeat dispatcher backed by a Redis sorted set.

    Instantiate once and call ``start()`` inside the application lifespan.
    ``stop()`` cancels the polling task gracefully.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._tasks: set = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Populate sorted set from DB, then launch polling loop."""
        if self._running:
            return
        self._running = True
        await self._repopulate_schedule()
        self._task = asyncio.create_task(self._poll_loop(), name="heartbeat-scheduler")
        logger.info("HeartbeatScheduler started")

    async def stop(self) -> None:
        """Cancel polling loop, drain in-flight adapter tasks, and exit cleanly."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        logger.info("HeartbeatScheduler stopped")

    # ------------------------------------------------------------------
    # Schedule population (restart-safe)
    # ------------------------------------------------------------------

    async def _repopulate_schedule(self) -> None:
        """Load all enabled agents and write their next fire times to Redis.

        Uses ZADD NX so existing scores survive a restart without clock
        skew — only agents not yet in the set are added.
        """
        redis = await get_async_redis_client()
        if redis is None:
            logger.error("Redis unavailable — heartbeat schedule not populated")
            return

        agents = await self._load_enabled_agents()
        if not agents:
            logger.info("No heartbeat-enabled agents found on startup")
            return

        now = datetime.now(tz=timezone.utc).timestamp()
        mapping: Dict[str, float] = {}
        for agent in agents:
            cron_expr = agent.get("heartbeat_cron")
            agent_id = agent["agent_id"]
            if not cron_expr:
                continue
            try:
                next_ts = _next_fire(cron_expr, now)
            except (ValueError, KeyError) as exc:
                logger.warning("Invalid cron for agent %s: %s", agent_id, exc)
                continue
            mapping[agent_id] = next_ts

        if mapping:
            # NX = add only when member does not exist (skip existing schedules)
            await redis.zadd(_SCHEDULE_KEY, mapping, nx=True)
            logger.info("Scheduled %d agents in sorted set", len(mapping))

    async def _load_enabled_agents(self) -> list[Dict[str, Any]]:
        """SELECT heartbeat-enabled agents from agent_org_nodes.

        company_id is stored directly on agent_org_nodes (migration 037, GH#8225).
        """
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT aon.agent_id, aon.name, aon.heartbeat_cron,
                           aon.adapter_type, aon.adapter_config, aon.context_mode,
                           aon.company_id
                    FROM agent_org_nodes aon
                    WHERE aon.heartbeat_enabled = true
                      AND aon.heartbeat_cron IS NOT NULL
                    """
                )
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self._dispatch_due()
            except Exception:
                logger.exception("Heartbeat poll error")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _dispatch_due(self) -> None:
        redis = await get_async_redis_client()
        if redis is None:
            return

        now = datetime.now(tz=timezone.utc).timestamp()
        due: list[bytes] = await redis.zrangebyscore(_SCHEDULE_KEY, 0, now)
        if not due:
            return

        for raw in due:
            agent_id = raw.decode() if isinstance(raw, bytes) else raw
            # Atomic claim: zrem returns 0 if another worker already took it
            removed = await redis.zrem(_SCHEDULE_KEY, agent_id)
            if not removed:
                continue
            try:
                await self._handle_due_agent(agent_id, redis)
            except Exception:
                logger.exception(
                    "Heartbeat dispatch error for agent %s; re-queuing in %ds",
                    agent_id,
                    int(_POLL_INTERVAL),
                )
                retry_ts = datetime.now(tz=timezone.utc).timestamp() + _POLL_INTERVAL
                await redis.zadd(_SCHEDULE_KEY, {agent_id: retry_ts})

    async def _handle_due_agent(self, agent_id: str, redis: Any) -> None:
        """Create run record, dispatch adapter, advance sorted-set score."""
        factory = get_async_session_factory()
        async with factory() as session:
            agent = await self._get_agent_config(session, agent_id)
            if agent is None:
                # Agent no longer enabled — remove from sorted set
                await redis.zrem(_SCHEDULE_KEY, agent_id)
                return

            cron_expr = agent.get("heartbeat_cron")
            if not cron_expr:
                await redis.zrem(_SCHEDULE_KEY, agent_id)
                return

            try:
                run = await self._create_run(
                    session,
                    agent=agent,
                    source=HeartbeatInvocationSource.SCHEDULER,
                )
            except ValueError as exc:
                logger.warning(
                    "Skipping heartbeat for agent %s (no organization): %s", agent_id, exc
                )
                await redis.zrem(_SCHEDULE_KEY, agent_id)
                return
            await session.commit()

        t = asyncio.create_task(
            self._run_adapter(agent, run.id),
            name=f"heartbeat-adapter-{agent_id}",
        )
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

        now = datetime.now(tz=timezone.utc).timestamp()
        try:
            next_ts = _next_fire(cron_expr, now)
        except Exception:
            logger.exception("Invalid cron for agent %s — removing from schedule", agent_id)
            await redis.zrem(_SCHEDULE_KEY, agent_id)
            return
        await redis.zadd(_SCHEDULE_KEY, {agent_id: next_ts})
        logger.debug(
            "Dispatched heartbeat for agent=%s run=%s next=%.0f",
            agent_id,
            run.id,
            next_ts,
        )

    # ------------------------------------------------------------------
    # Manual trigger (called from API)
    # ------------------------------------------------------------------

    async def trigger_manual(
        self,
        session: AsyncSession,
        agent_id: str,
    ) -> tuple[LLCHeartbeatRun, Dict[str, Any]]:
        """Flush a QUEUED run record; caller must commit then call dispatch_run.

        Returns (run, agent_cfg) so the caller can fire the adapter task after
        the DB commit is visible to other connections (avoids the race where
        _run_adapter's RUNNING UPDATE matches 0 rows because the INSERT is
        still uncommitted).
        """
        agent = await self._get_agent_config(session, agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id!r} not found or not configured")

        run = await self._create_run(
            session,
            agent=agent,
            source=HeartbeatInvocationSource.MANUAL,
        )
        await session.flush()
        return run, agent

    def dispatch_run(self, agent: Dict[str, Any], run_id: uuid.UUID) -> None:
        """Schedule adapter execution as a fire-and-forget task.

        Must be called after the DB session containing the run INSERT has been
        committed — ensures _run_adapter's RUNNING status UPDATE is visible.
        """
        t = asyncio.create_task(
            self._run_adapter(agent, run_id),
            name=f"heartbeat-manual-{agent['agent_id']}",
        )
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _get_agent_config(
        self, session: AsyncSession, agent_id: str
    ) -> Optional[Dict[str, Any]]:
        result = await session.execute(
            text(
                """
                SELECT aon.agent_id, aon.name, aon.heartbeat_cron, aon.heartbeat_enabled,
                       aon.adapter_type, aon.adapter_config, aon.context_mode,
                       aon.company_id
                FROM agent_org_nodes aon
                WHERE aon.agent_id = :agent_id
                  AND aon.heartbeat_enabled = true
                """
            ),
            {"agent_id": agent_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def _create_run(
        self,
        session: AsyncSession,
        agent: Dict[str, Any],
        source: HeartbeatInvocationSource,
    ) -> LLCHeartbeatRun:
        company_id_raw = agent.get("company_id")
        if company_id_raw is None:
            raise ValueError(f"Agent {agent['agent_id']!r} has no organization — cannot create heartbeat run")
        company_id = company_id_raw if isinstance(company_id_raw, uuid.UUID) else uuid.UUID(str(company_id_raw))
        run = LLCHeartbeatRun(
            id=uuid.uuid4(),
            company_id=company_id,
            agent_id=agent["agent_id"],
            invocation_source=source.value,
            status=HeartbeatRunStatus.QUEUED.value,
        )
        session.add(run)
        return run

    async def _run_adapter(self, agent: Dict[str, Any], run_id: uuid.UUID) -> None:
        """Execute adapter, update run status on completion/failure."""
        factory = get_async_session_factory()
        try:
            async with factory() as session:
                await session.execute(
                    update(LLCHeartbeatRun)
                    .where(LLCHeartbeatRun.id == run_id)
                    .values(
                        status=HeartbeatRunStatus.RUNNING.value,
                        started_at=datetime.now(tz=timezone.utc),
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.exception("Failed to mark run %s as RUNNING — marking FAILED", run_id)
            try:
                async with factory() as session:
                    await session.execute(
                        update(LLCHeartbeatRun)
                        .where(LLCHeartbeatRun.id == run_id)
                        .values(
                            status=HeartbeatRunStatus.FAILED.value,
                            finished_at=datetime.now(tz=timezone.utc),
                            error=str(exc),
                        )
                    )
                    await session.commit()
            except Exception:
                logger.exception("Could not write FAILED status for run %s", run_id)
            return

        error_msg: Optional[str] = None
        final_status = HeartbeatRunStatus.SUCCEEDED.value
        try:
            await _dispatch_adapter(agent)
        except Exception as exc:
            logger.exception("Adapter error for run %s", run_id)
            error_msg = str(exc)
            final_status = HeartbeatRunStatus.FAILED.value

        async with factory() as session:
            await session.execute(
                update(LLCHeartbeatRun)
                .where(LLCHeartbeatRun.id == run_id)
                .values(
                    status=final_status,
                    finished_at=datetime.now(tz=timezone.utc),
                    error=error_msg,
                )
            )
            # Only bump last_heartbeat_at on success — failures must not mask stale agents
            if final_status == HeartbeatRunStatus.SUCCEEDED.value:
                await session.execute(
                    text(
                        "UPDATE agent_org_nodes SET last_heartbeat_at = now() "
                        "WHERE agent_id = :aid"
                    ),
                    {"aid": agent["agent_id"]},
                )
            await session.commit()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _next_fire(cron_expr: str, base_ts: float) -> float:
    """Return the next scheduled epoch (float) after *base_ts*."""
    base_dt = datetime.fromtimestamp(base_ts, tz=timezone.utc)
    itr = croniter(cron_expr, base_dt)
    return itr.get_next(float)


async def _dispatch_adapter(agent: Dict[str, Any]) -> None:
    """Invoke the configured adapter for this agent.

    Currently a no-op placeholder — the adapter dispatch layer
    (GH#8226) will inject its implementation here.
    """
    adapter_type = agent.get("adapter_type") or "noop"
    logger.debug("Dispatching adapter=%s for agent=%s", adapter_type, agent["agent_id"])
    # Adapter framework (GH#8226) will replace this stub.
    await asyncio.sleep(0)
