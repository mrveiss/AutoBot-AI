# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical health-probe registry — single source of truth for /api/system/health.

Issue #3333 / #6902: 45 scattered per-module ``/health`` route definitions were
consolidated behind one aggregator (Phase 1–3, PR #6870) and then deleted (Phase 4,
PR #6902). Modules register a probe via :func:`register_health_probe`; the aggregator
at ``api/system.py`` runs every registered probe in parallel and merges their statuses
into a single ``SystemHealth`` response.

Probes MUST be async, accept an optional ``Request`` (so they can reach
``request.app.state``), and return :class:`ComponentHealth`. Probes that raise
or time out are recorded as ``status="down"`` — they MUST NOT crash the
aggregator.
"""

from __future__ import annotations

import asyncio
import enum
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

from fastapi import Request
from pydantic import BaseModel

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class KnownProbes(str, enum.Enum):
    """Canonical probe-name constants — single source of truth.

    Issue #6917: both backend probes and frontend callers previously
    hardcoded probe name strings independently. Using this enum at
    registration time makes a typo an immediate ImportError/AttributeError
    rather than a silent runtime fallback.

    Frontend code should import these values via the OpenAPI schema or
    reference this file's docstring when adding a new frontend caller.
    """

    BATCH_JOBS = "batch_jobs"
    LONG_RUNNING = "long_running"
    KNOWLEDGE = "knowledge"
    ERROR_RESILIENCE = "error_resilience"
    INTELLIGENT_AGENT = "intelligent_agent"
    LLC = "llc"
    PRICING = "pricing"  # GH#6480
    CONTENT_REACH = "content_reach"  # #10932


# Per-probe timeout. Probes slower than this become ``status="down"`` so a slow
# component cannot hold the aggregator hostage.
_PROBE_TIMEOUT_S = 2.0

HealthStatus = Literal["ok", "degraded", "down"]


class ComponentHealth(BaseModel):
    """Per-component result returned by a probe."""

    name: str
    status: HealthStatus
    detail: str | None = None
    latency_ms: float | None = None
    data: dict | None = None


class SystemHealth(BaseModel):
    """Aggregated system health — worst-of-components rollup."""

    status: HealthStatus
    components: list[ComponentHealth]
    timestamp: datetime


ProbeFn = Callable[[Request | None], Awaitable[ComponentHealth]]

_PROBES: dict[str, ProbeFn] = {}


def register_health_probe(name: str) -> Callable[[ProbeFn], ProbeFn]:
    """Decorator: register an async health probe under ``name``.

    Re-registering the same name overwrites and logs a warning — the
    rightmost import wins. This avoids duplicate-registration crashes when a
    module is reloaded (e.g. tests).

    #6918: rejects sync probes at registration time. ``_run_probe`` enforces
    ``_PROBE_TIMEOUT_S`` via ``asyncio.wait_for``, but ``wait_for`` only
    cancels at ``await`` points — a sync probe that blocks the event loop
    (e.g. ``time.sleep``, sync ``redis.ping``) holds the aggregator past the
    timeout. The aggregator's documented invariant ("a slow component
    cannot hold the aggregator hostage") is only true when every probe is
    properly async. Catch the obvious case at registration; this shifts a
    silent-prod-hang into an immediate import-time TypeError.
    """

    def _decorate(fn: ProbeFn) -> ProbeFn:
        if not asyncio.iscoroutinefunction(fn):
            raise TypeError(
                f"register_health_probe({name!r}): probe must be `async def` — "
                f"sync probes block the event loop and cannot be cancelled by "
                f"the {_PROBE_TIMEOUT_S}s timeout. See #6918."
            )
        if name in _PROBES:
            logger.warning("register_health_probe: %r already registered, overwriting", name)
        _PROBES[name] = fn
        return fn

    return _decorate


async def _run_probe(name: str, fn: ProbeFn, request: Request | None) -> ComponentHealth:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(fn(request), timeout=_PROBE_TIMEOUT_S)
    except asyncio.TimeoutError:
        return ComponentHealth(
            name=name,
            status="down",
            detail=f"probe timed out after {_PROBE_TIMEOUT_S}s",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:
        logger.warning("Health probe %r raised %s: %s", name, type(exc).__name__, exc)
        # Issue #10460: surface the message, not just the type, so a "down"
        # status is actionable (this endpoint is admin-only — no info leak).
        reason = str(exc).strip() or "no detail"
        return ComponentHealth(
            name=name,
            status="down",
            detail=f"probe error: {type(exc).__name__}: {reason[:160]}",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    if result.latency_ms is None:
        result = result.model_copy(update={"latency_ms": round((time.perf_counter() - started) * 1000, 2)})
    return result


def _aggregate_status(components: list[ComponentHealth]) -> HealthStatus:
    if any(c.status == "down" for c in components):
        return "down"
    if any(c.status == "degraded" for c in components):
        return "degraded"
    return "ok"


async def collect_system_health(
    request: Request | None = None,
) -> SystemHealth:
    """Run every registered probe concurrently and return an aggregated result."""
    if not _PROBES:
        return SystemHealth(
            status="ok",
            components=[],
            timestamp=datetime.now(tz=timezone.utc),
        )
    tasks = [_run_probe(n, fn, request) for n, fn in _PROBES.items()]
    components = await asyncio.gather(*tasks)
    return SystemHealth(
        status=_aggregate_status(components),
        components=components,
        timestamp=datetime.now(tz=timezone.utc),
    )


def list_registered_probes() -> list[str]:
    """Return the names of every currently-registered probe (sorted)."""
    return sorted(_PROBES.keys())


def _reset_probes_for_testing() -> None:
    """Clear the registry. Test-only — DO NOT call in production code."""
    _PROBES.clear()


# ----------------------------------------------------------------------------
# Composable probe helpers (Issue #6904)
# ----------------------------------------------------------------------------
#
# Inspecting the 38 probes registered after #6903 showed three patterns
# accounting for ~40% of all probe bodies:
#
#   1. **singleton-resolve** — call a getter, ok if it returns non-None
#   2. **redis-ping**       — async-ping a named Redis database
#   3. **app-state-attr**   — verify ``request.app.state.X`` is initialized
#
# The factories below return a ``ProbeFn`` ready to pass to
# ``register_health_probe(name)``; the ``register_*_probe`` convenience
# wrappers do both in one line:
#
#   register_singleton_probe("vision", get_screen_analyzer)
#   register_redis_probe("redis", database="main")
#   register_app_state_probe("memory", "memory_graph")
#
# Probes that need richer logic stay hand-written.


def probe_singleton(
    probe_name: str,
    getter: Callable,
    *,
    async_getter: bool = False,
    data_callback: Callable[[Any], dict] | None = None,
) -> ProbeFn:
    """Build a probe that resolves a singleton via ``getter`` and reports ok if non-None.

    Use ``async_getter=True`` when the getter is an async function that needs
    to be awaited (e.g. ``get_async_redis_client`` style factories).

    ``data_callback(instance)`` is called with the resolved instance (or
    ``None`` on failure) and its return value is attached as ``data`` on the
    ``ComponentHealth`` — use this instead of hand-writing the probe when you
    need module-specific fields in ``probes[name].data`` (#6914).
    """

    async def _probe(request: Request | None = None) -> ComponentHealth:
        try:
            instance = await getter() if async_getter else getter()
            if instance is None:
                return ComponentHealth(
                    name=probe_name,
                    status="down",
                    detail="singleton returned None",
                    data=data_callback(None) if data_callback else None,
                )
            return ComponentHealth(
                name=probe_name,
                status="ok",
                data=data_callback(instance) if data_callback else None,
            )
        except Exception as exc:
            # Issue #10460: include the message so the cause is visible
            # (e.g. which import/arg failed), not just the exception type.
            reason = str(exc).strip() or "no detail"
            return ComponentHealth(
                name=probe_name,
                status="down",
                detail=f"probe error: {type(exc).__name__}: {reason[:160]}",
                data=data_callback(None) if data_callback else None,
            )

    return _probe


def probe_redis_db(
    probe_name: str,
    *,
    database: str = "main",
    data_callback: Callable[[bool], dict] | None = None,
) -> ProbeFn:
    """Build a probe that pings ``database`` via the async Redis client.

    Always uses ``await get_async_redis_client(...) + await client.ping()`` so
    no probe blocks the asyncio event loop (regression class fixed in PR #6870).

    ``data_callback(ok)`` is called with ``True`` when the ping succeeds and
    ``False`` otherwise; its return value is attached as ``data`` on the
    ``ComponentHealth`` — use this to include module-specific fields such as
    ``redis_connected`` without hand-writing the probe (#6914).
    """

    async def _probe(request: Request | None = None) -> ComponentHealth:
        try:
            from autobot_shared.redis_client import get_async_redis_client

            client = await get_async_redis_client(database=database)
            if client is None:
                return ComponentHealth(
                    name=probe_name,
                    status="down",
                    detail=f"redis client unavailable (database={database})",
                    data=data_callback(False) if data_callback else None,
                )
            ok = True
            try:
                await client.ping()
            except Exception:
                ok = False
            return ComponentHealth(
                name=probe_name,
                status="ok" if ok else "down",
                detail=None if ok else "redis ping failed",
                data=data_callback(ok) if data_callback else None,
            )
        except Exception as exc:
            return ComponentHealth(
                name=probe_name,
                status="down",
                detail=f"probe error: {type(exc).__name__}",
                data=data_callback(False) if data_callback else None,
            )

    return _probe


def probe_app_state(
    probe_name: str,
    attr: str,
    *,
    data_callback: Callable[[Any], dict] | None = None,
) -> ProbeFn:
    """Build a probe that checks ``request.app.state.<attr>`` is initialized.

    Returns ``degraded`` when the attribute is missing (e.g. internal callers
    without a request context) and ``down`` when it is explicitly ``None``.

    ``data_callback(value)`` is called with the attribute value (or ``None``
    on failure) and its return value is attached as ``data`` on the
    ``ComponentHealth`` (#6914).
    """

    async def _probe(request: Request | None = None) -> ComponentHealth:
        if request is None or not hasattr(request.app.state, attr):
            return ComponentHealth(
                name=probe_name,
                status="degraded",
                detail=f"app.state.{attr} not initialized",
                data=data_callback(None) if data_callback else None,
            )
        try:
            value = getattr(request.app.state, attr)
            if value is None:
                return ComponentHealth(
                    name=probe_name,
                    status="down",
                    detail=f"app.state.{attr} is None",
                    data=data_callback(None) if data_callback else None,
                )
            return ComponentHealth(
                name=probe_name,
                status="ok",
                data=data_callback(value) if data_callback else None,
            )
        except Exception as exc:
            # Issue #10460: include the message so the cause is visible
            # (e.g. which import/arg failed), not just the exception type.
            reason = str(exc).strip() or "no detail"
            return ComponentHealth(
                name=probe_name,
                status="down",
                detail=f"probe error: {type(exc).__name__}: {reason[:160]}",
                data=data_callback(None) if data_callback else None,
            )

    return _probe


def register_singleton_probe(
    name: str,
    getter: Callable,
    *,
    async_getter: bool = False,
    data_callback: Callable[[Any], dict] | None = None,
) -> None:
    """One-line wrapper: build + register a singleton-resolve probe."""
    register_health_probe(name)(probe_singleton(name, getter, async_getter=async_getter, data_callback=data_callback))


def register_redis_probe(
    name: str,
    *,
    database: str = "main",
    data_callback: Callable[[bool], dict] | None = None,
) -> None:
    """One-line wrapper: build + register a Redis-ping probe."""
    register_health_probe(name)(probe_redis_db(name, database=database, data_callback=data_callback))


def register_app_state_probe(
    name: str,
    attr: str,
    *,
    data_callback: Callable[[Any], dict] | None = None,
) -> None:
    """One-line wrapper: build + register an app.state.<attr> probe."""
    register_health_probe(name)(probe_app_state(name, attr, data_callback=data_callback))
