# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data sources for the tiered L0-L4 context stack (#5066, GH#6469).

The layers in :mod:`chat_history.layers` are pure renderers — they read what the
caller puts in the context dict and render nothing when it is absent. Two of
them were therefore permanently silent in production because the call site never
supplied their input:

* **L2 OnDemand** (#13686) read ``memory_graph`` off the chat *workflow* manager,
  which has no such attribute. The graph lives on the chat *history* manager.
* **L4 GoalAncestry** (#13687) was never passed a ``goal_ancestry`` argument at
  all, so ``should_load(None)`` was always False.

This module owns the resolution of both inputs so the fix is testable without
constructing a ``ChatWorkflowManager``, and so neither resolver can take a
prompt-building turn down: both return None on any failure.
"""

from __future__ import annotations

import uuid
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


async def resolve_goal_ancestry(work_item_id: str | None) -> list | None:
    """Return the root-first goal ancestry chain for a work item, or None (#13687).

    ``work_item_id`` is the governed identity already lifted from the request
    context by ``build_governed_identity`` (GH#11160). A turn that carries no
    work item is the common case: it must cost **no** DB round-trip, which is
    why the falsy check comes before the session factory.

    Returns None (never raises) so a goal-lookup failure leaves L4 silent
    instead of failing the turn.
    """
    if not work_item_id:
        return None
    try:
        return await _query_goal_ancestry(work_item_id)
    except Exception as exc:
        logger.warning("Goal ancestry lookup failed for work item %s: %s", work_item_id, exc)
        return None


async def _query_goal_ancestry(work_item_id: str) -> list | None:
    """Resolve work item -> goal_id -> ancestry chain against the LLC store.

    Split from :func:`resolve_goal_ancestry` to keep the imports lazy (the LLC
    stack is optional at import time) and both functions inside the 30-line
    limit.
    """
    from llc.services.goal import GoalService
    from llc.services.work_item_service import WorkItemService
    from user_management.database import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as session:
        work_item = await WorkItemService().get(session, work_item_id)
        goal_id = getattr(work_item, "goal_id", None) if work_item else None
        if not goal_id:
            return None
        if not isinstance(goal_id, uuid.UUID):
            goal_id = uuid.UUID(str(goal_id))
        chain = await GoalService().get_goal_ancestry_for_work_item(session, goal_id)
        return chain or None


__all__ = ["resolve_memory_graph", "resolve_goal_ancestry"]
