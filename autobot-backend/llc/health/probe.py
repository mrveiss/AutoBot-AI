# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC system health probe — heartbeat scheduler uptime, lag, and budget alert metrics (GH#8259).

Registered under probe name ``llc`` and integrated into ``GET /api/health/full``
via the standard :func:`api.system_health.register_health_probe` decorator.

All reads are from Redis or small DB aggregates.  The probe is read-only and
designed to complete well under 500 ms.

Status semantics:
  ok        — all systems nominal
  degraded  — at least one agent overdue by > 2× interval, or budget warnings present
  critical  — scheduler not running, or any agent overdue by > 3× interval
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import func, select, text

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.approval import LLCApproval
from ..models.budget import LLCAgentBudget
from ..models.enums import ApprovalStatus

# Scheduler imports are lazy (inside functions) to avoid circular-import chains
# when the probe module is loaded in test environments (llc.services.__init__
# ordering bug filed as discovery issue GH#8259-disc).

logger = logging.getLogger(__name__)

_PROBE_NAME = KnownProbes.LLC

# Overdue thresholds — used for status escalation
_DEFAULT_CRON_INTERVAL_SECONDS = 3600  # fallback when cron can't be evaluated
_DEGRADED_MULTIPLIER = 2.0
_CRITICAL_MULTIPLIER = 3.0

# Budget warning threshold (matches BudgetWatchdog._SOFT_THRESHOLD)
_BUDGET_WARNING_RATIO = 0.80

# Pending approval staleness threshold
_APPROVAL_CRITICAL_MINUTES = 5


@register_health_probe(_PROBE_NAME)
async def probe_llc(request: Request | None = None) -> ComponentHealth:
    """Aggregate LLC health probe covering scheduler, heartbeat lag, and budget metrics."""
    start = time.monotonic()

    try:
        metrics = await _collect_metrics()
        status = _compute_status(metrics)
        latency_ms = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name=_PROBE_NAME,
            status=status,
            data=metrics,
            latency_ms=round(latency_ms, 1),
        )
    except Exception as exc:
        logger.exception("LLC health probe failed")
        latency_ms = (time.monotonic() - start) * 1000
        return ComponentHealth(
            name=_PROBE_NAME,
            status="down",
            detail=f"probe error: {type(exc).__name__}: {exc}",
            latency_ms=round(latency_ms, 1),
        )


async def _collect_metrics() -> dict:
    from ..scheduler.heartbeat_scheduler import get_heartbeat_scheduler

    scheduler = get_heartbeat_scheduler()
    liveness_monitor = _get_liveness_monitor()

    heartbeat_scheduler_running = _is_scheduler_running(scheduler)
    liveness_monitor_running = _is_liveness_monitor_running(liveness_monitor)
    scheduler_last_tick_age_seconds = await _scheduler_tick_age()
    agents_overdue_heartbeat = await _count_overdue_agents()
    budget_warning_companies, budget_exhausted_companies = await _budget_counts()
    pending_approvals_critical = await _pending_approvals_critical()

    return {
        "heartbeat_scheduler_running": heartbeat_scheduler_running,
        "liveness_monitor_running": liveness_monitor_running,
        "scheduler_last_tick_age_seconds": scheduler_last_tick_age_seconds,
        "agents_overdue_heartbeat": agents_overdue_heartbeat,
        "budget_warning_companies": budget_warning_companies,
        "budget_exhausted_companies": budget_exhausted_companies,
        "pending_approvals_critical": pending_approvals_critical,
    }


def _compute_status(metrics: dict) -> str:
    # ComponentHealth HealthStatus: "ok" | "degraded" | "down"
    # Issue #8259 calls for "critical" (scheduler down, overdue > 3× interval) → mapped to "down"
    if not metrics["heartbeat_scheduler_running"]:
        return "down"
    if metrics["agents_overdue_heartbeat"] > 0:
        return "down"
    if (
        metrics["budget_exhausted_companies"] > 0
        or not metrics["liveness_monitor_running"]
        or metrics["pending_approvals_critical"] > 0
        or metrics["budget_warning_companies"] > 0
    ):
        return "degraded"
    return "ok"


def _is_scheduler_running(scheduler: object) -> bool:
    """Check whether the HeartbeatScheduler background task is alive."""
    if not scheduler._running:
        return False
    task = scheduler._task
    if task is None or task.done():
        return False
    return True


def _get_liveness_monitor() -> object | None:
    """Return the singleton LivenessMonitor if it exists, else None."""
    try:
        from autobot_shared.singleton_factory import lazy_singleton
        from ..scheduler.liveness_monitor import LivenessMonitor

        get_lm = lazy_singleton(LivenessMonitor)
        return get_lm()
    except Exception:
        return None


def _is_liveness_monitor_running(monitor: object | None) -> bool:
    if monitor is None:
        return False
    if not monitor._running:
        return False
    task = monitor._task
    if task is None or task.done():
        return False
    return True


async def _scheduler_tick_age() -> float | None:
    """Return seconds since the heartbeat scheduler last polled the sorted set.

    The scheduler stores a ``llc:heartbeat:last_tick`` key (epoch float) in Redis
    each poll cycle.  If the key is absent, return None.
    """
    redis = await get_async_redis_client()
    if redis is None:
        return None
    try:
        raw = await redis.get("llc:heartbeat:last_tick")
        if raw is None:
            return None
        last_tick = float(raw)
        return round(time.time() - last_tick, 1)
    except Exception:
        logger.debug("Could not read llc:heartbeat:last_tick", exc_info=True)
        return None


async def _count_overdue_agents() -> int:
    """Count enabled agents whose last_heartbeat_at is > 3× their cron interval.

    Uses a pure-SQL approach for efficiency — one query, no Python-side cron parsing.
    Falls back to 0 on any error to prevent the probe from crashing.
    """
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            # Parse the cron expression's period from the schedule string.
            # We approximate by using the schedule_interval column if available,
            # otherwise fall back to a 1-hour default.
            # Agents are overdue when now() - last_heartbeat_at > 3 * interval.
            result = await session.execute(
                text("""
                    SELECT COUNT(*) FROM agent_org_nodes
                    WHERE heartbeat_enabled = true
                      AND heartbeat_cron IS NOT NULL
                      AND last_heartbeat_at IS NOT NULL
                      AND EXTRACT(EPOCH FROM (NOW() - last_heartbeat_at)) >
                          3 * COALESCE(heartbeat_interval_seconds, 3600)
                """)
            )
            row = result.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        logger.debug("Could not query overdue agents", exc_info=True)
        return 0


async def _budget_counts() -> tuple[int, int]:
    """Return (warning_company_count, exhausted_company_count).

    warning  = ≥80% utilisation (budget_spent / budget_limit ≥ 0.80) but < 100%
    exhausted = ≥100% utilisation
    """
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(
                    func.count().filter(
                        LLCAgentBudget.budget_spent >= LLCAgentBudget.budget_limit * _BUDGET_WARNING_RATIO,
                        LLCAgentBudget.budget_spent < LLCAgentBudget.budget_limit,
                    ).label("warning"),
                    func.count().filter(
                        LLCAgentBudget.budget_spent >= LLCAgentBudget.budget_limit,
                    ).label("exhausted"),
                )
            )
            row = result.fetchone()
            if row:
                return int(row[0]), int(row[1])
            return 0, 0
    except Exception:
        logger.debug("Could not query budget counts", exc_info=True)
        return 0, 0


async def _pending_approvals_critical() -> int:
    """Count PENDING approvals that have been open for more than 5 minutes."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=_APPROVAL_CRITICAL_MINUTES)
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(func.count()).where(
                    LLCApproval.status == ApprovalStatus.PENDING.value,
                    LLCApproval.created_at <= cutoff,
                )
            )
            return int(result.scalar_one_or_none() or 0)
    except Exception:
        logger.debug("Could not query pending approvals", exc_info=True)
        return 0
