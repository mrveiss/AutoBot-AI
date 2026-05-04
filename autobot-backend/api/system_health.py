# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Canonical health-probe registry — single source of truth for /api/system/health.

Issue #3333: 45 scattered ``@router.get("/health")`` definitions are being
consolidated behind one aggregator. Modules register a probe via
:func:`register_health_probe`; the aggregator at ``api/system.py`` runs every
registered probe in parallel and merges their statuses into a single
``SystemHealth`` response.

Probes MUST be async, accept an optional ``Request`` (so they can reach
``request.app.state``), and return :class:`ComponentHealth`. Probes that raise
or time out are recorded as ``status="down"`` — they MUST NOT crash the
aggregator.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable, Literal, Optional

from fastapi import Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Per-probe timeout. Probes slower than this become ``status="down"`` so a slow
# component cannot hold the aggregator hostage.
_PROBE_TIMEOUT_S = 2.0

HealthStatus = Literal["ok", "degraded", "down"]


class ComponentHealth(BaseModel):
    """Per-component result returned by a probe."""

    name: str
    status: HealthStatus
    detail: Optional[str] = None
    latency_ms: Optional[float] = None
    data: Optional[dict] = None


class SystemHealth(BaseModel):
    """Aggregated system health — worst-of-components rollup."""

    status: HealthStatus
    components: list[ComponentHealth]
    timestamp: datetime


ProbeFn = Callable[[Optional[Request]], Awaitable[ComponentHealth]]

_PROBES: dict[str, ProbeFn] = {}


def register_health_probe(name: str) -> Callable[[ProbeFn], ProbeFn]:
    """Decorator: register an async health probe under ``name``.

    Re-registering the same name overwrites and logs a warning — the
    rightmost import wins. This avoids duplicate-registration crashes when a
    module is reloaded (e.g. tests).
    """

    def _decorate(fn: ProbeFn) -> ProbeFn:
        if name in _PROBES:
            logger.warning(
                "register_health_probe: %r already registered, overwriting", name
            )
        _PROBES[name] = fn
        return fn

    return _decorate


async def _run_probe(
    name: str, fn: ProbeFn, request: Optional[Request]
) -> ComponentHealth:
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
        logger.warning("Health probe %r raised %s", name, type(exc).__name__)
        return ComponentHealth(
            name=name,
            status="down",
            detail=f"probe error: {type(exc).__name__}",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    if result.latency_ms is None:
        result = result.model_copy(
            update={
                "latency_ms": round((time.perf_counter() - started) * 1000, 2)
            }
        )
    return result


def _aggregate_status(components: list[ComponentHealth]) -> HealthStatus:
    if any(c.status == "down" for c in components):
        return "down"
    if any(c.status == "degraded" for c in components):
        return "degraded"
    return "ok"


async def collect_system_health(
    request: Optional[Request] = None,
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
