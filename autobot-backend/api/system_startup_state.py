# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Startup facts ``GET /api/health`` reports beside its status (GH#8947, #20232).

Neither field here changes ``status``: a load balancer that reads ``status`` must see the same
answer it saw before the field existed. They are for the operator reading the body.
"""

import asyncio
import json

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import STARTUP_ERROR_FILE

logger = get_logger(__name__)


async def resolve_startup_error(app_state: dict) -> str | None:
    """The exception type name of a failed startup, or None.

    Only the type name is exposed -- never the message, which may contain credentials
    (connection strings, Redis URLs). The in-memory value may be "TypeName: message"; Phase 1
    failures kill the process before ``app_state`` is reachable, so the disk file written by
    ``lifespan.py`` before re-raising is the fallback.
    """
    startup_error = app_state.get("startup_error")
    if startup_error:
        return startup_error.split(":")[0].strip()
    try:
        if await asyncio.to_thread(STARTUP_ERROR_FILE.exists):
            text = await asyncio.to_thread(STARTUP_ERROR_FILE.read_text, encoding="utf-8")
            return json.loads(text).get("error_type")
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning("Startup error file unreadable (%s); reporting no startup error", type(exc).__name__)
    return None


def company_os_scheduling() -> dict:
    """Whether Company OS cron dispatch is running, from the source ``GET /api/llc/health/probe`` reads.

    ``heartbeat_scheduler_running`` is None when the state could not be read, which is not False:
    "not running yet" and "could not tell" need different responses from an operator.
    """
    try:
        from llc.health.probe import heartbeat_scheduler_running

        return {"heartbeat_scheduler_running": heartbeat_scheduler_running()}
    except Exception as exc:  # noqa: BLE001 - a field about scheduling must not take the health answer down
        logger.warning("Company OS scheduling state unavailable: %s", type(exc).__name__)
        return {"heartbeat_scheduler_running": None}
