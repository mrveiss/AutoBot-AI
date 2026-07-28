# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Health probe for the backend→SLM control link (#12781).

The link fails closed and quietly: after a few rejected handshakes the client
pins its reconnect backoff to the maximum interval and stops logging, so the
node keeps serving traffic while the control plane sees nothing from it. On the
node in #12781 both reporting paths were down at once, which is why the
`autobot-backend` crash loop in #12777 was invisible in the GUI.

Nothing surfaced that state anywhere a human or a monitor would look. This
probe does, through the standard aggregator, so a broken control link shows up
as a degraded component instead of a line in a log nobody reads.
"""

import time
from typing import Optional

from fastapi import Request

from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from autobot_shared.logging_manager import get_logger
from services.slm_client import slm_link_state

logger = get_logger(__name__)

_PROBE_NAME = KnownProbes.SLM_LINK


def _status_for(state: dict) -> tuple[str, Optional[str]]:
    """Map a link snapshot onto (status, detail).

    ``backoff_pinned`` is the meaningful escalation, not the raw failure count:
    it marks a link that has stopped trying rather than one mid-retry, which is
    the state that persists until a restart.
    """
    if not state["initialized"]:
        return "down", "SLM client not initialized — this node cannot reach the control plane"

    if state["connected"]:
        return "ok", None

    if state["backoff_pinned"]:
        return "down", (
            f"control link down after {state['auth_failures']} rejected handshakes; "
            "reconnect backoff pinned to its maximum, so it will not recover without a "
            "restart. Check that AUTOBOT_JWT_SECRET on the backend matches SLM_SECRET_KEY "
            "on the SLM host."
        )

    return "degraded", f"control link reconnecting ({state['auth_failures']} failures so far)"


@register_health_probe(_PROBE_NAME)
async def probe_slm_link(request: Request | None = None) -> ComponentHealth:
    """Report whether this node's control-plane link is actually up."""
    start = time.monotonic()
    try:
        state = slm_link_state()
        status, detail = _status_for(state)
        return ComponentHealth(
            name=_PROBE_NAME,
            status=status,
            detail=detail,
            data=state,
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("SLM link health probe failed")
        return ComponentHealth(
            name=_PROBE_NAME,
            status="down",
            detail=f"probe error: {type(exc).__name__}: {exc}",
            latency_ms=round((time.monotonic() - start) * 1000, 1),
        )
