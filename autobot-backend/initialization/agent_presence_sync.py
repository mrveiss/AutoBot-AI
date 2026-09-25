# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Periodic caller of the presence-registry adapters (#16947, #16965 review).

Extracted out of `initialization/lifespan.py` rather than added there: that
module is grandfathered at a fixed size and may not grow (#14236) -- the
same reason `chat_workflow/tool_dispatch_guards.py` and
`llc/services/org_chart_rows.py` exist as siblings of their own oversized
files. `lifespan.py` calls `start()`/`stop()` here; everything else is local.

Without a caller, `sync_company_os_presence`/`sync_ai_stack_presence`/
`sync_session_presence` and `get_presence_registry` had zero production
callers -- the registry existed but nothing ever populated it. This is that
caller: one loop, every kind's own sync, on an interval comfortably under
the registry's own TTL (`AUTOBOT_AGENT_PRESENCE_TTL_SECONDS`, default 90s)
so an entry never goes stale between sweeps.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)

SYNC_INTERVAL_ENV = "AUTOBOT_AGENT_PRESENCE_SYNC_INTERVAL_SECONDS"
DEFAULT_SYNC_INTERVAL_SECONDS = 30.0
#: A 0 or negative interval would make `asyncio.sleep` return immediately,
#: busy-spinning _sync_once()'s DB session, Redis and health-registry reads
#: every tick -- clamped to a minimum of 1s (#16965 review), matching the
#: EnvVarSpec's own `range=`.
MIN_SYNC_INTERVAL_SECONDS = 1.0
MAX_SYNC_INTERVAL_SECONDS = 3600.0


def sync_interval_seconds() -> float:
    return env_float_clamped(
        SYNC_INTERVAL_ENV,
        DEFAULT_SYNC_INTERVAL_SECONDS,
        min_v=MIN_SYNC_INTERVAL_SECONDS,
        max_v=MAX_SYNC_INTERVAL_SECONDS,
    )


async def start(app: "FastAPI") -> None:
    """Start the periodic sync (NON-CRITICAL) -- called from lifespan Phase 2."""
    logger.info("Agent Presence Sync: starting...")
    try:
        app.state.agent_presence_sync_task = asyncio.create_task(_loop(), name="agent_presence_sync")
        logger.info("Agent Presence Sync: started")
    except Exception as presence_error:
        logger.warning("Agent presence sync initialization failed: %s", presence_error)


async def _sync_once() -> None:
    from agents.agent_client import get_agent_client
    from api.agent_terminal import get_agent_terminal_service
    from autobot_shared.redis_client import get_async_redis_client
    from chat_workflow import get_chat_workflow_manager
    from llc.services.agent_presence_queries import distinct_company_ids_with_agents
    from protocols.agent_presence import get_presence_registry
    from protocols.agent_presence_feeds import (
        sync_ai_stack_presence,
        sync_company_os_presence,
        sync_session_presence,
    )
    from user_management.database import get_async_session_factory

    registry = get_presence_registry()
    agent_client = await get_agent_client()
    # #17436: `get_redis_client(async_client=True)` is a SYNC function returning a
    # coroutine, so the un-awaited call handed the service a coroutine object as its
    # client -- and the service is a singleton, so startup order baked it in.
    terminal_service = get_agent_terminal_service(redis_client=await get_async_redis_client())

    await sync_ai_stack_presence(registry, agent_client.registry, get_chat_workflow_manager())
    await sync_session_presence(registry, terminal_service.session_manager)

    async with get_async_session_factory()() as session:
        for company_id in await distinct_company_ids_with_agents(session):
            try:
                await sync_company_os_presence(registry, session, company_id)
            except Exception as company_error:
                logger.warning("Presence sync failed for company %s: %s", company_id, company_error)


async def _loop() -> None:
    interval = sync_interval_seconds()
    while True:
        try:
            await _sync_once()
        except asyncio.CancelledError:
            raise
        except Exception as sync_error:
            logger.warning("Agent presence sync iteration failed: %s", sync_error)
        await asyncio.sleep(interval)
