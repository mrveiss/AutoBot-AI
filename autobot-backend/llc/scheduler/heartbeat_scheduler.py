# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    from croniter import croniter as _croniter_cls
except ImportError:
    _croniter_cls = None  # type: ignore[assignment]  # croniter not installed
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.env_utils import env_float
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..adapters import AdapterRunStatus, AutoBotAgentAdapter, get_adapter
from ..adapters.subprocess_base import is_subprocess_adapter
from ..config import AGENT_API_BASE_URL
from ..exceptions import (
    AdapterRunFailed,
    BudgetExhausted,
    HeartbeatDispatchSkipped,
    ProviderRateLimited,
    SubscriptionQuotaExhausted,
)
from ..models.enums import HeartbeatInvocationSource, LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..services.api_key import ApiKeyService
from ..services.budget import BudgetService
from ..services.controls_service import ControlsService
from ..services.replay_service import RunReplayService, parse_jsonl_events

logger = logging.getLogger(__name__)

_SCHEDULE_KEY = "llc:heartbeat:schedule"
_POLL_INTERVAL = 5.0  # seconds between sorted-set polls

# Rate-limit backoff: delay = min(_RL_BASE_SECONDS * 2**retry_count, _RL_MAX_SECONDS)
_RL_BASE_SECONDS = 300  # 5 minutes for the first retry
_RL_MAX_SECONDS = 14400  # cap at 4 hours
_MAX_RATE_LIMIT_RETRIES = 10  # demote to failed after this many consecutive retries


# Registry-adapter (e.g. claude_code) completion polling (GH#9622, GH#9623).
_ADAPTER_POLL_INTERVAL = env_float("LLC_ADAPTER_POLL_INTERVAL_SECONDS", 5.0)
_ADAPTER_MAX_WAIT_SECONDS = env_float("LLC_ADAPTER_MAX_WAIT_SECONDS", 7200.0)
# Ephemeral run-key TTL backstop — must exceed the max wait so a key never
# expires mid-run; revocation still happens promptly when the run finishes.
_RUN_KEY_TTL_SECONDS = env_float("LLC_RUN_KEY_TTL_SECONDS", _ADAPTER_MAX_WAIT_SECONDS + 600.0)


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
        quota_exc: Optional[SubscriptionQuotaExhausted] = None
        external_run_id: Optional[str] = None

        try:
            external_run_id = await _dispatch_adapter(agent, context)
        except ProviderRateLimited as exc:
            rate_limited_exc = exc
        except SubscriptionQuotaExhausted as exc:
            quota_exc = exc
        except HeartbeatDispatchSkipped as exc:
            # GH#9951: not dispatched → record SKIPPED, do NOT bump last_heartbeat_at.
            logger.info("Heartbeat skipped for run %s: %s", run_id, exc.reason)
            final_status = LLCRunStatus.SKIPPED.value
            error_msg = exc.reason
        except Exception as exc:
            logger.exception("Adapter error for run %s", run_id)
            error_msg = str(exc)
            final_status = LLCRunStatus.FAILED.value

        if rate_limited_exc is not None:
            await self._handle_rate_limited(agent, run_id, retry_count, rate_limited_exc)
            return

        if quota_exc is not None:
            await self._handle_quota_exhausted(agent, run_id, quota_exc)
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

        # GH#9034: fire-and-forget replay recording — must never affect run status.
        # Pass external_run_id so the recording locates the exact output file (H1).
        # GH#9951: a SKIPPED run never dispatched, so there is nothing to record.
        if final_status != LLCRunStatus.SKIPPED.value:
            _record_task = asyncio.create_task(
                _record_run_for_replay(agent, run_id, context, final_status, external_run_id=external_run_id),
                name=f"replay-record-{run_id}",
            )
            self._tasks.add(_record_task)
            _record_task.add_done_callback(self._tasks.discard)

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

    async def _handle_quota_exhausted(
        self,
        agent: Dict[str, Any],
        run_id: uuid.UUID,
        exc: SubscriptionQuotaExhausted,
    ) -> None:
        """Record the run ``quota_exhausted`` and auto-pause the agent (GH#10218).

        A subscription quota is spent for the billing window, so — unlike
        RATE_LIMITED — retrying is futile. ``ControlsService.pause_agent`` flips
        the agent to ``paused`` AND logs a board-visible ``CONTROL_AGENT_PAUSED``
        event (the board notification), so a human resumes it after topping up.
        """
        agent_id = agent["agent_id"]
        company_id = str(agent.get("company_id") or "")
        factory = get_async_session_factory()
        try:
            async with factory() as session:
                await session.execute(
                    update(LLCHeartbeatRun)
                    .where(LLCHeartbeatRun.id == run_id)
                    .values(
                        status=LLCRunStatus.QUOTA_EXHAUSTED.value,
                        finished_at=datetime.now(tz=timezone.utc),
                        error=exc.reason,
                    )
                )
                if company_id:
                    await ControlsService().pause_agent(
                        session,
                        company_id,
                        agent_id,
                        actor_user_id=None,
                        reason=f"subscription quota exhausted (run {run_id})",
                        actor_type="system",
                    )
                else:
                    logger.warning("Agent %s quota-exhausted but has no company_id — not auto-paused", agent_id)
                await session.commit()
            logger.warning("Agent %s auto-paused: %s (run %s)", agent_id, exc.reason, run_id)
        except Exception:
            logger.exception("Could not record quota-exhausted / pause agent %s for run %s", agent_id, run_id)


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


async def _record_run_for_replay(
    agent: Dict[str, Any],
    run_id: uuid.UUID,
    context: Dict[str, Any],
    final_status: str,
    *,
    external_run_id: Optional[str] = None,
) -> None:
    """Best-effort replay recording fired after a run reaches terminal status (GH#9034).

    For subprocess adapters the JSONL output file is resolved via the adapter's
    ``_output_path`` helper using the exact ``external_run_id`` returned by
    ``adapter.invoke`` — no mtime glob, no concurrent-run collision (H1 fix).
    For in-process agents there is no file; recorded_events is stored as None.
    Any exception is swallowed so the scheduler is never blocked.
    """
    import asyncio as _asyncio
    import os as _os

    try:
        output_text: Optional[str] = None
        recorded_events = None

        adapter_type = agent.get("adapter_type") or "autobot_agent"
        if adapter_type != "autobot_agent" and external_run_id is not None:
            # Resolve the exact output file via the adapter's own path helper.
            cfg = agent.get("adapter_config") or {}
            output_dir: str = cfg.get("output_dir", "/tmp")  # nosec B108
            agent_id_str = str(agent.get("agent_id", ""))
            output_file: Optional[str] = None
            try:
                from ..adapters.claude_code_adapter import _output_path as _cc_output_path

                output_file = _cc_output_path(output_dir, agent_id_str, external_run_id)
            except ImportError:
                pass

            if output_file and _os.path.exists(output_file):
                try:
                    raw: str = await _asyncio.to_thread(_read_file_text, output_file)
                    from ..services.replay_service import _REPLAY_OUTPUT_CAP

                    output_text = raw[-_REPLAY_OUTPUT_CAP:] if len(raw) > _REPLAY_OUTPUT_CAP else raw
                    recorded_events = parse_jsonl_events(raw)
                except OSError:
                    pass

        svc = RunReplayService()
        await svc.record_run(
            run_id=run_id,
            agent=agent,
            context=context,
            final_status=final_status,
            output_text=output_text,
            recorded_events=recorded_events,
        )
    except Exception:
        logger.exception("_record_run_for_replay: unexpected error for run %s", run_id)


def _read_file_text(path: str) -> str:
    """Read a file as text — runs in a thread via asyncio.to_thread (M4)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _next_fire(cron_expr: str, base_ts: float) -> float:
    """Return the next scheduled epoch (float) after *base_ts*."""
    if _croniter_cls is None:
        raise RuntimeError("croniter is required for heartbeat scheduling — pip install croniter")
    base_dt = datetime.fromtimestamp(base_ts, tz=timezone.utc)
    itr = _croniter_cls(cron_expr, base_dt)
    return itr.get_next(float)


async def _dispatch_adapter(agent: Dict[str, Any], context: Dict[str, Any]) -> Optional[str]:
    """Route the heartbeat to the adapter configured for this agent.

    Returns the external_run_id produced by the adapter (for subprocess adapters),
    or None for in-process / skipped dispatches.

    ``autobot_agent`` agents run in-process via :class:`AutoBotAgentAdapter`
    (GH#8490).  Every other ``adapter_type`` resolves through the adapter
    registry (GH#8226) — e.g. ``claude_code`` agents run as Claude Code CLI
    subprocesses (GH#9622, GH#9623).  Registry adapters are issued an
    ephemeral, run-scoped LLC API key so the woken agent can authenticate its
    LLC API calls; the key is revoked when the run finishes.
    """
    adapter_type = agent.get("adapter_type") or "autobot_agent"
    logger.debug(
        "Dispatching adapter=%s for agent=%s context_keys=%s",
        adapter_type,
        agent["agent_id"],
        sorted(context.keys()),
    )

    if adapter_type == "autobot_agent":
        await _dispatch_autobot_agent(agent, context)
        return None

    try:
        adapter = get_adapter(adapter_type)
    except KeyError:
        # GH#9951: signal a skip (not a phantom COMPLETED) so the run is
        # recorded as SKIPPED and last_heartbeat_at is not advanced.
        raise HeartbeatDispatchSkipped(
            agent["agent_id"], f"no LLC adapter registered for type {adapter_type!r}"
        ) from None

    # GH#9793: skip dispatch when the required CLI binary is absent from PATH.
    # Converts every-heartbeat FAILED runs into a clean degraded state (GH#9951).
    if is_subprocess_adapter(adapter) and not adapter.is_cli_available():  # type: ignore[union-attr]
        raise HeartbeatDispatchSkipped(
            agent["agent_id"],
            f"adapter {adapter_type!r} requires CLI "
            f"{adapter._required_cli!r} which is not on PATH",  # type: ignore[union-attr]
        )

    return await _dispatch_registry_adapter(adapter, agent, context)


async def _dispatch_autobot_agent(agent: Dict[str, Any], context: Dict[str, Any]) -> None:
    """Dispatch an in-process AutoBot agent via :class:`AutoBotAgentAdapter`."""
    adapter_config = agent.get("adapter_config") or {}
    if not adapter_config.get("agent_class"):
        # No agent_class configured — degraded skip, not a phantom success (GH#9951).
        raise HeartbeatDispatchSkipped(
            agent["agent_id"],
            "no adapter_config.agent_class configured",
        )

    # GH#8502: use run_blocking() so ProviderRateLimited propagates to _run_adapter
    # and triggers exponential-backoff recovery.  _run_adapter is already a
    # background task, so blocking here does not stall the poll loop.
    adapter = AutoBotAgentAdapter(agent_config=adapter_config)
    await adapter.run_blocking(dict(context, agent_id=agent["agent_id"]))


async def _dispatch_registry_adapter(adapter: Any, agent: Dict[str, Any], context: Dict[str, Any]) -> Optional[str]:
    """Invoke a registry adapter, manage its run-scoped key, await completion.

    Returns the external_run_id string produced by ``adapter.invoke`` so callers
    can resolve the exact output file (H1 fix — no mtime glob needed).

    Issues an ephemeral LLC API key scoped to this agent (GH#9623), injects it
    plus the API base URL into the context so the adapter forwards them to the
    subprocess, blocks until the external run reaches a terminal state, then
    revokes the key — so the credential lives only for the duration of the run.

    RATE_LIMITED terminal state (GH#9773): when the adapter signals that the
    external run hit a provider rate limit, this function raises
    ``ProviderRateLimited`` so ``_run_adapter``'s existing exponential-backoff
    path (GH#8204) applies uniformly for registry adapters — the run is not
    recorded as FAILED, the checkout is preserved, and the agent is re-queued
    at the computed retry-after time.
    """
    agent_id: str = agent["agent_id"]
    company_id = str(agent.get("company_id") or "")

    key_record = None
    enriched = dict(context, agent_id=agent_id, api_base=AGENT_API_BASE_URL)
    if company_id:
        key_record, raw_key = await _issue_run_key(agent_id, company_id)
        if raw_key:
            # Sensitive: plaintext run-scoped bearer token — never log this value.
            enriched["agent_api_key"] = raw_key
    else:
        logger.warning("agent %s has no company_id — dispatching without an LLC API key", agent_id)

    # GH#10217: include company_id so subscription adapters can resolve
    # company-scoped credential secrets (e.g. gh_token_secret) at invoke time.
    agent_config = {
        "agent_id": agent_id,
        "company_id": company_id,
        "adapter_config": agent.get("adapter_config") or {},
    }
    external_run_id: Optional[str] = None
    try:
        external_run_id = await adapter.invoke(agent_config, enriched)
        result = await _await_adapter_completion(adapter, agent_config, external_run_id)
        final_status = result.status
    except asyncio.CancelledError:
        # Shutdown / task cancellation — kill the external run so it does not
        # outlive its about-to-be-revoked key, then propagate.
        if external_run_id is not None:
            await _safe_cancel(adapter, agent_config, external_run_id)
        raise
    finally:
        if key_record is not None:
            await _revoke_run_key(agent_id, key_record.id)

    # GH#9773: RATE_LIMITED is scheduler-internal — translate to ProviderRateLimited
    # so the GH#8204 backoff path applies uniformly for registry adapters.
    # This exception is caught by _run_adapter which then calls _handle_rate_limited.
    # It never reaches the DB as a RATE_LIMITED terminal adapter status.
    if final_status == LLCRunStatus.RATE_LIMITED:
        logger.warning(
            "agent %s: registry adapter signalled RATE_LIMITED for run %s — raising ProviderRateLimited",
            agent_id,
            external_run_id,
        )
        raise ProviderRateLimited(provider=agent.get("adapter_type") or "registry", retry_after_seconds=0)

    # GH#10218: subscription quota exhausted is terminal-with-no-retry — surface
    # it so _run_adapter auto-pauses the agent + notifies the board rather than
    # recording a generic FAILED that the liveness monitor would try to recover.
    if final_status == LLCRunStatus.QUOTA_EXHAUSTED:
        raise SubscriptionQuotaExhausted(agent_id, str(result.error or "subscription quota exhausted"))

    # GH#9622: surface non-success terminal states so _run_adapter records the
    # run as FAILED (and the liveness monitor can act) instead of COMPLETED.
    if final_status != LLCRunStatus.COMPLETED:
        raise AdapterRunFailed(agent.get("adapter_type") or "", str(external_run_id), final_status)

    # GH#10220: forward parsed token usage to the agent's budget. BudgetExhausted
    # is re-raised (GH#8215 hard-stop → run marked FAILED); other cost errors are
    # best-effort and never fail an otherwise-successful run.
    await _ingest_adapter_usage(agent, result)

    return external_run_id


async def _ingest_adapter_usage(agent: Dict[str, Any], result: AdapterRunStatus) -> None:
    """Record a completed registry run's token usage against the agent budget."""
    if result.tokens_in is None and result.tokens_out is None:
        return  # adapter did not report usage (e.g. CLI without stream-json result)
    agent_id: str = agent["agent_id"]
    model = (agent.get("adapter_config") or {}).get("model") or agent.get("model") or ""
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            await BudgetService().ingest_cost_event(
                session,
                agent_id,
                int(result.tokens_in or 0),
                int(result.tokens_out or 0),
                model,
            )
            await session.commit()
    except BudgetExhausted:
        raise  # GH#8215 hard-stop — propagate so the run is recorded FAILED
    except Exception:
        logger.warning("Budget ingest failed for agent %s (best-effort)", agent_id)


async def _safe_cancel(adapter: Any, agent_config: Dict[str, Any], run_id: str) -> None:
    """Cancel an external run, swallowing adapter errors (best-effort)."""
    try:
        await adapter.cancel(agent_config, run_id)
    except Exception:
        logger.exception("Failed to cancel adapter run %s", run_id)


async def _issue_run_key(agent_id: str, company_id: str) -> tuple[Any, Optional[str]]:
    """Issue an ephemeral run-scoped LLC API key. Returns (record, plaintext).

    Best-effort: on failure the agent still runs, just without a key (returns
    ``(None, None)``) — the run is logged rather than blocked.
    """
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            record, raw = await ApiKeyService().issue_key(
                session,
                agent_id=agent_id,
                company_id=company_id,
                name=f"heartbeat-{agent_id}-{uuid.uuid4().hex[:8]}",
                expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=_RUN_KEY_TTL_SECONDS),
            )
        return record, raw
    except Exception:
        logger.exception("Failed to issue ephemeral heartbeat key for agent %s", agent_id)
        return None, None


async def _revoke_run_key(agent_id: str, key_id: uuid.UUID) -> None:
    """Revoke an ephemeral run-scoped key (best-effort)."""
    factory = get_async_session_factory()
    try:
        async with factory() as session:
            await ApiKeyService().revoke_key(session, agent_id=agent_id, key_id=key_id)
    except Exception:
        logger.exception("Failed to revoke ephemeral heartbeat key %s for agent %s", key_id, agent_id)


async def _await_adapter_completion(adapter: Any, agent_config: Dict[str, Any], run_id: str) -> AdapterRunStatus:
    """Poll ``adapter.status`` until the run is terminal or the max wait elapses.

    Returns the full terminal :class:`AdapterRunStatus` (carrying token usage for
    billing, GH#10220). Cancels the run if it overruns
    ``_ADAPTER_MAX_WAIT_SECONDS`` so the ephemeral key is never left live forever.
    """
    started = time.monotonic()
    while time.monotonic() - started < _ADAPTER_MAX_WAIT_SECONDS:
        result = await adapter.status(agent_config, run_id)
        if result.status.is_terminal():
            return result
        await asyncio.sleep(_ADAPTER_POLL_INTERVAL)

    logger.warning("Adapter run %s exceeded max wait — cancelling", run_id)
    await adapter.cancel(agent_config, run_id)
    return AdapterRunStatus(status=LLCRunStatus.TIMEOUT)


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
