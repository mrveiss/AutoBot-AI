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

L4 GoalAncestry (#13687) is wired as of #13704, which supplied the two things
it needed: a server-side session→work-item binding
(:mod:`chat_workflow.session_work_item`) and a tenant-scoped goal lookup. The
work item is never read from the client-supplied request context — that would
have made an unscoped cross-tenant read out of a rendering fix.
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


async def resolve_goal_ancestry(session_id: str) -> list | None:
    """Return the root-first goal ancestry chain for a session, or None (#13687).

    Both the work item **and** the company come from the server-side session
    binding (:class:`chat_workflow.session_work_item.SessionWorkItemService`),
    which the bind endpoint wrote only after verifying the caller owns the
    session and the work item belongs to their company.

    Nothing here is taken from the request context. That is deliberate: the
    context bag is client-supplied, and ``session.metadata["company_id"]`` is
    assigned from it at ``chat_workflow/manager.py:3331``, so neither can serve
    as a tenant scope.

    A turn with no binding is the common case and must cost **no** DB round-trip,
    which is why the falsy check precedes the session factory. Returns None on
    any failure so a goal-lookup error leaves L4 silent rather than failing the
    turn.
    """
    work_item_id = None
    try:
        from chat_workflow.session_work_item import SessionWorkItemService

        binding = await SessionWorkItemService().get_binding(session_id)
        work_item_id, company_id = binding.work_item_id, binding.company_id
        if not work_item_id or not company_id:
            return None
        # Reject a malformed id before the membership round-trip (#13729): a
        # client-shaped mistake should not cost a query.
        if not _is_uuid(work_item_id):
            logger.debug("Ignoring malformed work_item_id for goal ancestry: %r", work_item_id)
            return None
        if not await _authorisation_still_holds(company_id, binding.user_id):
            return None
        return await _query_goal_ancestry(str(work_item_id), company_id)
    except Exception as exc:
        logger.warning("Goal ancestry lookup failed for work item %s: %s", work_item_id, exc)
        return None


def _is_uuid(value: str) -> bool:
    """True when *value* parses as a UUID."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


async def _authorisation_still_holds(company_id: str, user_id: str | None) -> bool:
    """Re-check the bound user's access to *company_id* at resolve time (#13729).

    The binding recorded a decision the bind endpoint made, and nothing expired
    it before ``SESSION_WORK_ITEM_TTL_SECONDS`` — so a user removed from the
    company kept receiving its goal chain for up to a day. This closes that
    window at the cost of one indexed membership lookup, and only on sessions
    that actually have a binding.

    Bindings written before #13729 carry no ``user_id``. They are refused rather
    than grandfathered: they expire within the TTL, and the alternative is to
    keep honouring exactly the unverifiable claim this fixes.

    A platform admin may bind a company they are not a member of, so the current
    admin flag is checked too — read from the database, never from the stored
    binding, so losing admin takes effect on the next turn as well.
    """
    if not user_id:
        logger.debug("Goal ancestry: binding predates user recording (#13729); treating as unauthorised")
        return False

    from llc.services.membership_service import MembershipService
    from user_management.database import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as session:
        if await MembershipService().is_member(session, company_id, user_id):
            return True
        if await _is_platform_admin(session, user_id):
            return True

    logger.info("Goal ancestry: user %s is no longer scoped to company %s; chain withheld", user_id, company_id)
    return False


async def _is_platform_admin(session, user_id: str) -> bool:
    """Return the user's *current* platform-admin flag (#13729)."""
    import uuid as _uuid  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from user_management.models import User  # noqa: PLC0415

    try:
        parsed = _uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return False
    result = await session.execute(select(User.is_platform_admin).where(User.id == parsed))
    return bool(result.scalar_one_or_none())


async def _query_goal_ancestry(work_item_id: str, company_id: str | None) -> list | None:
    """Resolve work item -> goal_id -> ancestry chain, scoped to *company_id*.

    Split out to keep the LLC imports lazy (the stack is optional at import
    time) and both functions inside the 30-line limit.
    """
    if not _is_uuid(work_item_id):
        # A malformed id is a client-shaped problem, not a system failure —
        # debug, not a per-turn warning. Also checked by the caller, before the
        # membership round-trip; kept here for any direct caller.
        logger.debug("Ignoring malformed work_item_id for goal ancestry: %r", work_item_id)
        return None

    from llc.services.goal import GoalService
    from llc.services.work_item_service import WorkItemService
    from user_management.database import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as session:
        work_item = await WorkItemService().get(session, work_item_id, company_id=company_id)
        goal_id = getattr(work_item, "goal_id", None) if work_item else None
        if not goal_id:
            return None
        chain = await GoalService().get_goal_ancestry_for_work_item(session, goal_id, company_id=company_id)
        return chain or None


__all__ = ["resolve_goal_ancestry", "resolve_memory_graph"]
