# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Health probe for the startup first-admin link (#10200).

Registered on import, exactly as ``slm_link_probe``: the backend lifespan imports
this module, so importing ``person_link_service`` alone registers nothing.
"""

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from user_management.services import person_link_service as link

_PROBE_NAME = KnownProbes.FIRST_ADMIN_LINK

_HEALTH_BY_STATUS: dict[str, tuple[str, str | None]] = {
    link.LINK_OK: ("ok", None),
    link.LINK_KEY_MISSING: (
        "down",
        "no internal API key is configured, so the SLM's first admin was not linked",
    ),
    link.LINK_REFUSED: (
        "down",
        "the SLM refused the internal API key; the key differs between the backend and the SLM",
    ),
    link.LINK_NO_HASH: (
        "degraded",
        "the SLM's first admin has no password hash, so it was not linked and a default admin was seeded",
    ),
    link.LINK_FAILED: (
        "degraded",
        "the SLM's first admin could not be read; the admin was not linked and a default was seeded",
    ),
}


def _status_for(status: str | None) -> tuple[str, str | None]:
    """Map ``last_link_status`` onto (health status, detail) for the system health aggregator."""
    if status is None:
        return "idle", "first-admin link has not run yet"
    return _HEALTH_BY_STATUS.get(status, ("degraded", f"unrecognised first-admin link status: {status}"))


@register_health_probe(_PROBE_NAME)
async def probe_first_admin_link(request: Request | None = None) -> ComponentHealth:
    """Report the outcome of the startup first-admin link (#10200)."""
    status = link.last_link_status  # read at call time so the value stays live
    health, detail = _status_for(status)
    return ComponentHealth(name=_PROBE_NAME, status=health, detail=detail, data={"link_status": status})
