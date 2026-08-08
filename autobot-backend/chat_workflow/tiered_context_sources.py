# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data sources for the tiered L0-L4 context stack (#5066).

The layers in :mod:`chat_history.layers` are pure renderers — they read what the
caller puts in the context dict and render nothing when it is absent. L2
OnDemand was therefore permanently silent in production: `llm_handler` read
``memory_graph`` off the chat *workflow* manager, which has no such attribute
(#13686). The graph lives on the chat *history* manager.

L4 GoalAncestry is still dark, deliberately. Wiring it needs a server-side
session→work-item binding that does not exist yet, and a tenant-scoped goal
lookup — see the follow-up issue referenced from #13687. Sourcing the work item
from the client-supplied request context would have made an unscoped
cross-tenant read out of a rendering fix.
"""

from __future__ import annotations

from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def resolve_memory_graph() -> Any | None:
    """Return the app's initialised memory graph, or None (#13686).

    Reads ``.memory_graph`` off the process-wide ``ChatHistoryManager`` — the
    object that constructs and owns it (``chat_history/base.py:244``) behind an
    idempotent init and the ``memory_graph_enabled`` gate. No graph is
    constructed here; when the manager is absent or its graph failed to
    initialise, L2 degrades to an empty string exactly as designed.
    """
    try:
        from utils.resource_factory import ResourceFactory

        chm = ResourceFactory.get_initialized_chat_history_manager()
        if chm is None:
            logger.debug("Memory graph unavailable: no initialised ChatHistoryManager")
            return None
        return getattr(chm, "memory_graph", None)
    except Exception as exc:
        logger.warning("Memory graph resolution failed: %s", exc)
        return None


__all__ = ["resolve_memory_graph"]
