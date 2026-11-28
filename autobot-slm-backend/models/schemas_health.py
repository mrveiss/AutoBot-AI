# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM health response shape (#15462).

Its own module because ``models/schemas.py`` sits at its recorded size ceiling
and a grandfathered file may not grow (#14236). Adding one field to a health
response should not require shaving prose elsewhere, and this response has
grown twice now for the same reason — #14299 added ``redis`` after a backend
with an open circuit breaker reported healthy because Postgres answered, and
#15462 added ``frontend`` after ``/slm/`` served 403 for hours while every
field here described a process. It will grow again; it now has room to.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    uptime_seconds: float
    database: str
    # #15462: `/slm/` answered 403 for hours while this said "healthy" — every
    # field described a process, none the artifact a user loads.
    frontend: str = "unknown"
    # #22067: roles left out of the registry for want of a manifest: "unhealthy" plus the map below, never a crash.
    manifests: str = "healthy"
    manifest_errors: dict[str, str] = Field(default_factory=dict)
    # #14299: Redis was never part of this response — a backend with an open
    # circuit breaker on its main database still reported itself healthy, as
    # long as Postgres answered. Required (not Optional): the single caller
    # (api/health.py::health_check) always sets it.
    redis: str
    nodes_online: int
    nodes_total: int
