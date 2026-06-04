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

Rate-limit recovery (GH#8204):
  - Adapters raise ``ProviderRateLimited`` when the LLM provider rejects a
    request due to quota or rate limits.
  - ``_run_adapter`` catches this, marks the run ``rate_limited``, stores
    ``retry_after`` (exponential backoff, capped at 4 h), and re-queues the
    agent in Redis at ``retry_after`` instead of the next cron time.
  - The work item checkout is deliberately NOT released — the agent resumes
    the same item when limits reset.
  - ``_handle_due_agent`` detects retry fires (a ``rate_limited`` run exists
    for this agent) and resumes that run rather than creating a fresh one.
  - After ``_MAX_RATE_LIMIT_RETRIES`` consecutive rate-limit failures the run
    is demoted to ``failed`` so the liveness monitor can escalate normally.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from croniter import croniter as _croniter_cls
except ImportError:
    _croniter_cls = None  # type: ignore[assignment]  # croniter not installed
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..adapters import AutoBotAgentAdapter
from ..exceptions import ProviderRateLimited
from ..models.enums import HeartbeatInvocationSource, LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun

logger = logging.getLogger(__name__)

_SCHEDULE_KEY = "llc:heartbeat:schedule"
_POLL_INTERVAL = 5.0  # seconds between sorted-set polls

# Rate-limit backoff: delay = min(_RL_BASE_SECONDS * 2**retry_count, _RL_MAX_SECONDS)
_RL_BASE_SECONDS = 300  # 5 minutes for the first retry
_RL_MAX_SECONDS = 14400  # cap at 4 hours
_MAX_RATE_LIMIT_RETRIES = 10  # demote to failed after this many consecutive retries


class HeartbeatScheduler:
    """Cron-driven heartbeat dispatcher backed by a Redis sorted set.

    Instantiate once and call ``start()`` inside the application lifespan.
    ``stop()`` cancels the polling task gracefully.
    """

    def __init__(self) -> None:
        # GH#8494: store poll task as a named instance attribute to prevent GC
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False
        self._tasks: set = set()

    @property
    def is_running(self) -> bool:
        return self._running and self._poll_task is not None and not self._poll_task.done()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Populate sorted set from DB, then launch polling loop."""
        if self._running:
            return
        self._running = True
        await self._repopulate_schedule()
        # GH#8494: assign to self._poll_task so the reference is held and GC cannot
        # collect the task while the scheduler is running.
        self._poll_task = asyncio.create_task(self._poll_loop(), name="heartbeat-scheduler")
        logger.info("HeartbeatScheduler started")

    async def stop(self) -> None:
        """Cancel polling loop, drain in-flight adapter tasks, and exit cleanly."""
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
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

        Agents with an active ``rate_limited`` run keep their existing Redis
        score (the retry_after epoch written when the rate limit was hit) so a
        server restart does not reset the backoff.
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
            # GH#8498: use GT flag so existing scores are updated when the agent's
            # cron expression changes (next fire is later than the current score).
            # NX was previously used but prevented cron expression updates from
            # taking effect — an updated schedule would be silently ignored.
            await redis.zadd(_SCHEDULE_KEY, mapping, gt=True)
            logger.info("Scheduled %d agents in sorted set", len(mapping))

        # Re-queue any rate-limited agents whose retry_after is still in the
        # future — they may have been evicted from Redis if the server restarted.
        await self._restore_rate_limited_agents(redis)

    async def _restore_rate_limited_agents(self, redis: Any) -> None:
        """Re-queue agents with active rate_limited runs into the sorted set.

        Uses ZADD NX so we never overwrite an already-queued score — the
        existing score (cron next-fire) is always earlier or the same epoch.
        """
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(LLCHeartbeatRun).where(
                    LLCHeartbeatRun.status == LLCRunStatus.RATE_LIMITED.value,
                    LLCHeartbeatRun.retry_after.isnot(None),
                )
            )
            runs = list(result.scalars().all())

        mapping: Dict[str, float] = {}
        for run in runs:
            assert run.retry_after is not None  # checked in WHERE clause
            retry_ts = run.retry_after.timestamp()
            mapping[run.agent_id] = retry_ts

        if mapping:
            await redis.zadd(_SCHEDULE_KEY, mapping, nx=True)
            logger.info("Re-queued %d rate-limited agents after restart", len(mapping))

    async def _load_enabled_agents(self) -> list[Dict[str, Any]]:
        """SELECT heartbeat-enabled agents from agent_org_nodes.

        company_id is stored directly on agent_org_nodes (migration 037, GH#8225).
        """
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(text("""
                    SELECT aon.agent_id, aon.name, aon.heartbeat_cron,
                           aon.adapter_type, aon.adapter_config, aon.context_mode,
                           aon.company_id
                    FROM agent_org_nodes aon
                    WHERE aon.heartbeat_enabled = true
                      AND aon.heartbeat_cron IS NOT NULL
                    """))
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
        """Create (or resume) a run record, dispatch adapter, advance sorted-set score.

        Rate-limit retry path: if a ``rate_limited`` run exists for this agent,
        resume it (reset to QUEUED) and dispatch with the preserved
        ``context_snapshot`` rather than creating a fresh run.  This ensures
        the agent picks up the same checked-out work item it was working on
        when the rate limit was hit.
        """
        factory = get_async_session_factory()
        async with factory() as session:
            agent = await self._get_agent_config(session, agent_id)
            if agent is None:
                await redis.zrem(_SCHEDULE_KEY, agent_id)
                return

            cron_expr = agent.get("heartbeat_cron")
            if not cron_expr:
                await redis.zrem(_SCHEDULE_KEY, agent_id)
                return

            # Check for an active rate-limited run to resume.
            rate_limited_run = await self._find_rate_limited_run(session, agent_id)

            if rate_limited_run is not None:
                run = rate_limited_run
                context = run.context_snapshot or {}
                await session.execute(
                    update(LLCHeartbeatRun)
                    .where(LLCHeartbeatRun.id == run.id)
                    .values(
                        status=LLCRunStatus.QUEUED.value,
                        retry_after=None,
                    )
                )
                logger.info(
                    "Resuming rate-limited run %s for agent %s (retry #%d)",
                    run.id,
                    agent_id,
                    run.retry_count,
                )
            else:
                context = {}
                try:
                    run = await self._create_run(
                        session,
                        agent=agent,
                        source=HeartbeatInvocationSource.SCHEDULER,
                    )
                except ValueError as exc:
                    logger.warning("Skipping heartbeat for agent %s (no organization): %s", agent_id, exc)
                    retry_ts = datetime.now(tz=timezone.utc).timestamp() + _POLL_INTERVAL * 6
                    await redis.zadd(_SCHEDULE_KEY, {agent_id: retry_ts})
                    return

                # Enrich context with recent decisions when context_mode=fat (GH#8243)
                context_mode = agent.get("context_mode") or "slim"
                if context_mode == "fat":
                    company_id_val = agent.get("company_id")
                    if company_id_val:
                        context["recent_decisions"] = await _fetch_recent_decisions(str(company_id_val))

                # GH#8499: write context_snapshot so the field is never NULL.
                # For fat context include a generated_at timestamp; for slim/other
                # modes write the mode so diagnostics can confirm what was used.
                utc_now_iso = datetime.now(tz=timezone.utc).isoformat()
                if context_mode == "fat":
                    run.context_snapshot = {"mode": "fat", "generated_at": utc_now_iso}
                else:
                    run.context_snapshot = {"mode": context_mode}

            await session.commit()

        t = asyncio.create_task(
            self._run_adapter(agent, run.id, context),
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

    async def _find_rate_limited_run(self, session: AsyncSession, agent_id: str) -> Optional[LLCHeartbeatRun]:
        """Return the most recent ``rate_limited`` run for *agent_id*, or None."""
        result = await session.execute(
            select(LLCHeartbeatRun)
            .where(
                LLCHeartbeatRun.agent_id == agent_id,
                LLCHeartbeatRun.status == LLCRunStatus.RATE_LIMITED.value,
            )
            .order_by(LLCHeartbeatRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

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

    def dispatch_run(self, agent: Dict[str, Any], run_id: uuid.UUID, context: Optional[Dict[str, Any]] = None) -> None:
        """Schedule adapter execution as a fire-and-forget task.

        Must be called after the DB session containing the run INSERT has been
        committed — ensures _run_adapter's RUNNING status UPDATE is visible.
        """
        t = asyncio.create_task(
            self._run_adapter(agent, run_id, context or {}),
            name=f"heartbeat-manual-{agent['agent_id']}",
        )
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _get_agent_config(self, session: AsyncSession, agent_id: str) -> Optional[Dict[str, Any]]:
        result = await session.execute(
            text("""
                SELECT aon.agent_id, aon.name, aon.heartbeat_cron, aon.heartbeat_enabled,
                       aon.adapter_type, aon.adapter_config, aon.context_mode,
                       aon.company_id
                FROM agent_org_nodes aon
                WHERE aon.agent_id = :agent_id
                  AND aon.heartbeat_enabled = true
                """),
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
            status=LLCRunStatus.QUEUED.value,
        )
        session.add(run)
        return run

    async def _run_adapter(self, agent: Dict[str, Any], run_id: uuid.UUID, context: Dict[str, Any]) -> None:
        """Execute adapter, update run status on completion/failure.

        ProviderRateLimited is handled specially: the run is marked
        ``rate_limited`` with an exponential-backoff ``retry_after`` timestamp,
        the agent is re-queued in Redis, and the work item checkout is preserved
        so the next dispatch resumes where it left off.
        """
        factory = get_async_session_factory()

        # Fetch current retry_count before marking RUNNING so backoff is correct.
        try:
            async with factory() as session:
                result = await session.execute(select(LLCHeartbeatRun.retry_count).where(LLCHeartbeatRun.id == run_id))
                retry_count: int = result.scalar_one_or_none() or 0
                await session.execute(
                    update(LLCHeartbeatRun)
                    .where(LLCHeartbeatRun.id == run_id)
                    .values(
                        status=LLCRunStatus.RUNNING.value,
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
                            status=LLCRunStatus.FAILED.value,
                            finished_at=datetime.now(tz=timezone.utc),
                            error=str(exc),
                        )
                    )
                    await session.commit()
            except Exception:
                logger.exception("Could not write FAILED status for run %s", run_id)
            return

        error_msg: Optional[str] = None
        final_status = LLCRunStatus.COMPLETED.value
        rate_limited_exc: Optional[ProviderRateLimited] = None

        try:
            await _dispatch_adapter(agent, context)
        except ProviderRateLimited as exc:
            rate_limited_exc = exc
        except Exception as exc:
            logger.exception("Adapter error for run %s", run_id)
            error_msg = str(exc)
            final_status = LLCRunStatus.FAILED.value

        if rate_limited_exc is not None:
            await self._handle_rate_limited(agent, run_id, retry_count, rate_limited_exc)
            return

        try:
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
                if final_status == LLCRunStatus.COMPLETED.value:
                    await session.execute(
                        text("UPDATE agent_org_nodes SET last_heartbeat_at = now()" " WHERE agent_id = :aid"),
                        {"aid": agent["agent_id"]},
                    )
                await session.commit()
        except Exception:
            logger.exception("Could not write final status for run %s", run_id)

    async def _handle_rate_limited(
        self,
        agent: Dict[str, Any],
        run_id: uuid.UUID,
        retry_count: int,
        exc: ProviderRateLimited,
    ) -> None:
        """Persist rate_limited status, compute backoff, re-queue in Redis.

        The work item checkout key is intentionally left in Redis — the agent
        will reclaim the same item on the next dispatch.

        After _MAX_RATE_LIMIT_RETRIES consecutive rate-limit failures the run
        is demoted to ``failed`` so the liveness monitor can escalate it.
        """
        agent_id = agent["agent_id"]
        new_retry_count = retry_count + 1

        if new_retry_count > _MAX_RATE_LIMIT_RETRIES:
            logger.error(
                "Agent %s hit rate limit %d times (run %s) — demoting to FAILED",
                agent_id,
                new_retry_count,
                run_id,
            )
            factory = get_async_session_factory()
            try:
                async with factory() as session:
                    await session.execute(
                        update(LLCHeartbeatRun)
                        .where(LLCHeartbeatRun.id == run_id)
                        .values(
                            status=LLCRunStatus.FAILED.value,
                            finished_at=datetime.now(tz=timezone.utc),
                            error=f"Rate-limit retries exhausted ({new_retry_count}): {exc}",
                            retry_count=new_retry_count,
                        )
                    )
                    await session.commit()
            except Exception:
                logger.exception("Could not write FAILED status for rate-exhausted run %s", run_id)
            return

        # Exponential backoff: use provider hint if available, else compute.
        if exc.retry_after_seconds > 0:
            delay_seconds = exc.retry_after_seconds
        else:
            delay_seconds = min(_RL_BASE_SECONDS * (2**retry_count), _RL_MAX_SECONDS)

        retry_after_dt = datetime.now(tz=timezone.utc) + timedelta(seconds=delay_seconds)

        logger.warning(
            "Agent %s rate-limited by provider %r (run %s); retry #%d in %ds at %s",
            agent_id,
            exc.provider,
            run_id,
            new_retry_count,
            delay_seconds,
            retry_after_dt.isoformat(),
        )

        factory = get_async_session_factory()
        try:
            async with factory() as session:
                await session.execute(
                    update(LLCHeartbeatRun)
                    .where(LLCHeartbeatRun.id == run_id)
                    .values(
                        status=LLCRunStatus.RATE_LIMITED.value,
                        finished_at=datetime.now(tz=timezone.utc),
                        error=str(exc),
                        retry_after=retry_after_dt,
                        retry_count=new_retry_count,
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("Could not write RATE_LIMITED status for run %s", run_id)
            return

        # Re-queue the agent in Redis at retry_after so it fires automatically.
        try:
            redis = await get_async_redis_client()
            if redis is not None:
                retry_ts = retry_after_dt.timestamp()
                # Use XX (only update existing) + LT (only if new score is less) so we
                # never push the retry further into the future than the next cron tick.
                existing_score = await redis.zscore(_SCHEDULE_KEY, agent_id)
                if existing_score is None or retry_ts < float(existing_score):
                    await redis.zadd(_SCHEDULE_KEY, {agent_id: retry_ts})
        except Exception:
            logger.exception("Could not re-queue rate-limited agent %s in Redis for run %s", agent_id, run_id)


# ------------------------------------------------------------------
# Module-level singleton (shared between lifespan startup and API routes)
# ------------------------------------------------------------------

# One lazy_singleton call at module level so every import site gets the same instance.
# Do NOT call lazy_singleton(HeartbeatScheduler) at individual call sites — each call
# produces an independent closure with its own instance variable.
_get_scheduler = lazy_singleton(HeartbeatScheduler)


def get_heartbeat_scheduler() -> HeartbeatScheduler:
    """Return the process-wide HeartbeatScheduler singleton."""
    return _get_scheduler()


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _next_fire(cron_expr: str, base_ts: float) -> float:
    """Return the next scheduled epoch (float) after *base_ts*."""
    if _croniter_cls is None:
        raise RuntimeError("croniter is required for heartbeat scheduling — pip install croniter")
    base_dt = datetime.fromtimestamp(base_ts, tz=timezone.utc)
    itr = _croniter_cls(cron_expr, base_dt)
    return itr.get_next(float)


async def _dispatch_adapter(agent: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Invoke the configured adapter for this agent via AutoBotAgentAdapter.

    GH#8490: replaces the no-op stub with a real dispatch through
    ``AutoBotAgentAdapter`` so heartbeat runs actually execute agents.

    The adapter is instantiated per-call using the agent's ``adapter_config``
    (a JSON dict stored in ``agent_org_nodes.adapter_config``).  For agents
    without an explicit ``adapter_config`` or ``adapter_type`` we fall back to
    a minimal noop so existing rows are not broken during rollout.

    Adapters should raise ``ProviderRateLimited`` when the LLM provider
    rejects the request due to quota or rate limits so the scheduler can
    schedule an automatic retry rather than marking the run as failed.
    """
    adapter_type = agent.get("adapter_type") or "autobot_agent"
    adapter_config = agent.get("adapter_config") or {}

    logger.debug(
        "Dispatching adapter=%s for agent=%s context_keys=%s",
        adapter_type,
        agent["agent_id"],
        sorted(context.keys()),
    )

    if not adapter_config.get("agent_class"):
        # No agent_class configured — log and return (graceful degradation).
        logger.warning(
            "agent %s has no adapter_config.agent_class — skipping dispatch (configure agent_class to enable)",
            agent["agent_id"],
        )
        return

    # GH#8502: use run_blocking() so ProviderRateLimited propagates to _run_adapter
    # and triggers exponential-backoff recovery.  _run_adapter is already a
    # background task, so blocking here does not stall the poll loop.
    adapter = AutoBotAgentAdapter(agent_config=adapter_config)
    await adapter.run_blocking(dict(context, agent_id=agent["agent_id"]))


async def _fetch_recent_decisions(company_id: str, n: int = 5) -> list[Dict[str, Any]]:
    """Query the decisions KB for the most recent decisions (GH#8243).

    Used by heartbeat context building when context_mode=fat.  Best-effort —
    returns an empty list on any failure rather than blocking the heartbeat.
    """
    try:
        from ..kb.decision_log import DecisionLogReader

        reader = DecisionLogReader()
        return await reader.list_decisions(company_id=company_id, limit=n)
    except Exception as exc:
        logger.warning("Failed to fetch recent decisions for company %s: %s", company_id, exc)
        return []
