# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Content Reach health probe — AutoBot's `doctor` analog for content sources (#10932)."""

from __future__ import annotations

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from content_reach.registry import get_content_source_registry


@register_health_probe(KnownProbes.CONTENT_REACH)
async def probe_content_reach(request: Request | None = None) -> ComponentHealth:
    """Report per-source/per-backend liveness for content reach."""
    registry = get_content_source_registry()
    sources = registry.list_sources()
    name = KnownProbes.CONTENT_REACH.value

    if not sources:
        return ComponentHealth(name=name, status="down", detail="no content sources registered")

    live = await registry.probe_all()
    dead_sources = [s for s, live_backends in live.items() if not live_backends]

    if not dead_sources:
        status = "ok"
    elif len(dead_sources) < len(sources):
        status = "degraded"
    else:
        status = "down"

    return ComponentHealth(
        name=name,
        status=status,
        detail=f"{len(sources)} sources; dead: {dead_sources or 'none'}",
        data={"sources": sources, "live": live},
    )
