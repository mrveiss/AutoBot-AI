# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Step-up re-authentication gate — D2 (#10158).

Require recent authentication before elevated/sensitive operations such as
SSO provider management, provider secret rotation, and other
``SECURITY_MANAGE``-gated endpoints.

Design
------
The step-up check inspects the ``auth_time`` claim (OIDC standard — epoch
seconds of last authentication event) or falls back to the JWT ``iat``
(issued-at) when ``auth_time`` is absent.  If the authentication occurred
more than ``STEP_UP_MAX_AGE_SECONDS`` ago the dependency raises HTTP 401
with ``X-Step-Up-Required: true`` so the frontend can prompt for re-auth.

Configuration
-------------
``SLM_STEP_UP_MAX_AGE_SECONDS`` — env var, default 900 s (15 min).
Set to 0 to disable the freshness gate (emergency bypass; logs a warning).

Usage (FastAPI dependency)::

    @router.post("/sso-providers")
    async def create_provider(
        ...,
        _: dict = Depends(require_step_up),
        current_user: dict = Depends(require_permission(Permission.SECURITY_MANAGE)),
    ): ...

Or compose with permission gate via the pre-built factories at module bottom.
"""

import logging
import os
import time
from typing import Any, Dict

from fastapi import Depends, HTTPException, status

from services.auth import get_current_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constant — env var driven, never hard-coded
# ---------------------------------------------------------------------------

_ENV_MAX_AGE = "SLM_STEP_UP_MAX_AGE_SECONDS"
_STEP_UP_DEFAULT = 900  # 15 minutes


def _resolve_step_up_max_age() -> int:
    """Return the maximum auth age in seconds from env var or default."""
    raw = os.environ.get(_ENV_MAX_AGE, "")
    if not raw:
        return _STEP_UP_DEFAULT
    try:
        val = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; using default %d s", _ENV_MAX_AGE, raw, _STEP_UP_DEFAULT
        )
        return _STEP_UP_DEFAULT
    if val < 0:
        logger.warning("%s=%d is negative; treating as 0 (step-up disabled)", _ENV_MAX_AGE, val)
        return 0
    return val


#: Module-level constant resolved at import time — avoids repeated env lookups.
STEP_UP_MAX_AGE_SECONDS: int = _resolve_step_up_max_age()


# ---------------------------------------------------------------------------
# Core check — kept ≤30 lines, extracted for testability
# ---------------------------------------------------------------------------


def _is_auth_fresh(claims: Dict[str, Any], max_age: int) -> bool:
    """Return True when the authentication event is within *max_age* seconds.

    Checks ``auth_time`` (OIDC standard) first, then ``iat`` as fallback.
    Returns True (bypass) when max_age is 0 or no timestamp claim is present,
    so legacy HS256 tokens (no auth_time) are not hard-blocked.
    """
    if max_age == 0:
        return True
    now = int(time.time())
    auth_ts: int | None = None
    if "auth_time" in claims:
        try:
            auth_ts = int(claims["auth_time"])
        except (TypeError, ValueError):
            pass
    if auth_ts is None and "iat" in claims:
        try:
            auth_ts = int(claims["iat"])
        except (TypeError, ValueError):
            pass
    if auth_ts is None:
        # No timestamp available — pass-through; don't block legacy tokens.
        logger.debug("step_up_auth: no auth_time/iat claim; bypassing freshness check")
        return True
    age = now - auth_ts
    return age <= max_age


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def require_step_up(current_user: Dict = Depends(get_current_user)) -> Dict:
    """FastAPI dependency: enforce recent authentication for elevated operations.

    Injects after ``get_current_user`` so the user is already verified.
    Raises HTTP 401 with ``X-Step-Up-Required: true`` header when the
    authentication event is older than ``STEP_UP_MAX_AGE_SECONDS``.

    Usage::

        @router.post("/endpoint")
        async def endpoint(user: dict = Depends(require_step_up)): ...
    """
    if not _is_auth_fresh(current_user, STEP_UP_MAX_AGE_SECONDS):
        logger.info(
            "step_up_auth: stale auth for user %r — step-up required (max_age=%ds)",
            current_user.get("sub") or current_user.get("username"),
            STEP_UP_MAX_AGE_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Recent authentication required for this operation. Please re-authenticate.",
            headers={"X-Step-Up-Required": "true"},
        )
    return current_user
