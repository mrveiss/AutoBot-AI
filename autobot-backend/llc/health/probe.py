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

# HeartbeatScheduler import is lazy (inside _collect_metrics) to avoid circular-import
# chains when the probe module is loaded in test environments.
# LivenessMonitor singleton wrapper is created once at module level inside a try/except
# so it is cached for the process lifetime without forcing an import at module load in
# environments where the scheduler package is not yet available.
try:
    from autobot_shared.singleton_factory import lazy_singleton as _lazy_singleton

    from ..scheduler.liveness_monitor import LivenessMonitor as _LivenessMonitor

    _get_lm = _lazy_singleton(_LivenessMonitor)
except ImportError:
    _get_lm = None

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
    agents_overdue_degraded, agents_overdue_critical = await _count_overdue_agents()
    budget_warning_companies, budget_exhausted_companies = await _budget_counts()
    pending_approvals_critical = await _pending_approvals_critical()
    agents_missing_instructions = await _count_agents_missing_instructions()

    return {
        "heartbeat_scheduler_running": heartbeat_scheduler_running,
        "liveness_monitor_running": liveness_monitor_running,
        "scheduler_last_tick_age_seconds": scheduler_last_tick_age_seconds,
        "agents_overdue_degraded": agents_overdue_degraded,
        "agents_overdue_critical": agents_overdue_critical,
        "budget_warning_companies": budget_warning_companies,
        "budget_exhausted_companies": budget_exhausted_companies,
        "pending_approvals_critical": pending_approvals_critical,
        "agents_missing_instructions": agents_missing_instructions,
    }


def _compute_status(metrics: dict) -> str:
    # ComponentHealth HealthStatus: "ok" | "degraded" | "down"
    # Issue #8259 calls for "critical" (scheduler down, overdue > 3× interval) → mapped to "down"
    if not metrics["heartbeat_scheduler_running"]:
        return "down"
    if metrics["agents_overdue_critical"] > 0:
        return "down"
    if (
        metrics["agents_overdue_degraded"] > 0
        or metrics["budget_exhausted_companies"] > 0
        or not metrics["liveness_monitor_running"]
        or metrics["pending_approvals_critical"] > 0
        or metrics["budget_warning_companies"] > 0
        or metrics.get("agents_missing_instructions", 0) > 0
    ):
        return "degraded"
    return "ok"


def _is_scheduler_running(scheduler: object) -> bool:
    """Check whether the HeartbeatScheduler background task is alive."""
    return bool(getattr(scheduler, "is_running", False))


def _get_liveness_monitor() -> object | None:
    """Return the singleton LivenessMonitor if it exists, else None."""
    if _get_lm is None:
        return None
    try:
        return _get_lm()
    except Exception:
        return None


def _is_liveness_monitor_running(monitor: object | None) -> bool:
    return monitor is not None and bool(getattr(monitor, "is_running", False))


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


async def _count_overdue_agents() -> tuple[int, int]:
    """Return (degraded_count, critical_count) of enabled agents with stale heartbeats.

    degraded = lag > _DEGRADED_MULTIPLIER * _DEFAULT_CRON_INTERVAL_SECONDS
               and lag <= _CRITICAL_MULTIPLIER * _DEFAULT_CRON_INTERVAL_SECONDS
    critical = lag > _CRITICAL_MULTIPLIER * _DEFAULT_CRON_INTERVAL_SECONDS
    Falls back to (0, 0) on any error to prevent the probe from crashing.
    """
    try:
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(
                text("""
                    SELECT
                        COUNT(*) FILTER (
                            WHERE EXTRACT(EPOCH FROM (NOW() - last_heartbeat_at)) >
                                  :degraded_threshold
                              AND EXTRACT(EPOCH FROM (NOW() - last_heartbeat_at)) <=
                                  :critical_threshold
                        ) AS degraded_count,
                        COUNT(*) FILTER (
                            WHERE EXTRACT(EPOCH FROM (NOW() - last_heartbeat_at)) >
                                  :critical_threshold
                        ) AS critical_count
                    FROM agent_org_nodes
                    WHERE heartbeat_enabled = true
                      AND heartbeat_cron IS NOT NULL
                      AND last_heartbeat_at IS NOT NULL
                """).bindparams(
                    degraded_threshold=_DEGRADED_MULTIPLIER * _DEFAULT_CRON_INTERVAL_SECONDS,
                    critical_threshold=_CRITICAL_MULTIPLIER * _DEFAULT_CRON_INTERVAL_SECONDS,
                )
            )
            row = result.fetchone()
            if row:
                return int(row[0]), int(row[1])
            return 0, 0
    except Exception:
        logger.debug("Could not query overdue agents", exc_info=True)
        return 0, 0


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
                    func.count()
                    .filter(
                        LLCAgentBudget.budget_spent >= LLCAgentBudget.budget_limit * _BUDGET_WARNING_RATIO,
                        LLCAgentBudget.budget_spent < LLCAgentBudget.budget_limit,
                    )
                    .label("warning"),
                    func.count()
                    .filter(
                        LLCAgentBudget.budget_spent >= LLCAgentBudget.budget_limit,
                    )
                    .label("exhausted"),
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


async def _count_agents_missing_instructions() -> int:
    """Count heartbeat-enabled claude_code agents whose AGENTS.md is missing on disk (GH#8486).

    An agent running without an instructions file has no role definition or
    safety constraints — discovered in production on Paperclip (GH#8486, item 3).
    The probe flags these agents as degraded so operators can repair them via
    ``doctor --repair``.

    Returns the count of affected agents.  Falls back to 0 on any error so
    the probe does not crash when the column does not yet exist (pre-migration
    environments).
    """
    import os

    try:
        factory = get_async_session_factory()
        async with factory() as session:
            result = await session.execute(text("""
                    SELECT agent_id, instructions_file_path
                    FROM agent_org_nodes
                    WHERE heartbeat_enabled = true
                      AND adapter_type = 'claude_code'
                """))
            rows = result.fetchall()

        missing = 0
        for row in rows:
            path = row[1]  # instructions_file_path
            if not path or not os.path.isfile(path):
                missing += 1
        return missing
    except Exception:
        logger.debug("Could not query agents missing instructions", exc_info=True)
        return 0
