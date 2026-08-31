# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Wire a per-endpoint enforcement override into an authorization decision (#15086).

`FeatureFlags.get_endpoint_enforcement` (`services/feature_flags.py`) read its
key correctly -- it was never part of the `_redis` bug fixed for #15089. Its
defect was narrower: nothing called it. `set_endpoint_enforcement` and
`remove_endpoint_enforcement` (`api/feature_flags.py`) accept and audit-log a
per-endpoint override; `SessionOwnershipValidator` read only the global mode.
An operator could set an endpoint to `enforced`, see it accepted, audit-logged,
and read back -- and it never reached an authorization decision.

Split into its own module rather than added to `session_ownership.py`: that
file is grandfathered at its current size (#14236) and may not grow.
"""

from __future__ import annotations

from fastapi import Request

from autobot_shared.logging_manager import get_logger
from services.feature_flags import EnforcementMode, combine_enforcement_modes

logger = get_logger(__name__)


def route_pattern(request: Request) -> str:
    """The endpoint identity used to look up a per-endpoint override.

    Uses the route's path *template* (e.g. ``/api/chat/sessions/{session_id}``)
    when FastAPI has resolved one -- matching what an operator is told to write
    by ``set_endpoint_enforcement``'s docstring (`api/feature_flags.py`). Falls
    back to the concrete request path when routing has not attached a route, so
    a lookup never raises for want of one; that fallback simply matches no
    stored override.
    """
    route = getattr(request, "scope", {}).get("route") if hasattr(request, "scope") else None
    route_path = getattr(route, "path", None)
    return route_path if isinstance(route_path, str) and route_path else str(request.url.path)


async def effective_enforcement_mode(feature_flags, global_mode: str, request: Request) -> str:
    """Combine *global_mode* with any per-endpoint override for *request*'s route.

    The stricter of the two always wins -- see :func:`combine_enforcement_modes`
    for the precedence rule and its justification. A failed or absent override
    degrades to *global_mode* unchanged; it can never make the result weaker.
    """
    if feature_flags is None:
        return global_mode

    endpoint = route_pattern(request)
    try:
        override = await feature_flags.get_endpoint_enforcement(endpoint)
    except Exception as exc:
        logger.warning(
            "Could not read per-endpoint enforcement override for %s (%s); using global mode %s.",
            endpoint,
            exc,
            global_mode,
        )
        return global_mode

    return combine_enforcement_modes(EnforcementMode(global_mode), override).value
