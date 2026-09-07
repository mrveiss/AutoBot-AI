# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared route helpers for the LLC API surface.

``_actor_id`` and the error translators were written three times over
(``roles.py``, ``contacts.py``, ``workflows.py``) with identical bodies and
three different docstrings. This is the single copy; the existing three are
tracked for migration separately so that change stays reviewable on its own.

The actor rule is the one worth stating once and keeping stated: the acting
user comes from the authenticated session and never from the request body or
query. A client-supplied actor let the audit trail's identity and its
USER/SYSTEM discriminator be whatever the caller typed (#13969 review M1).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, Request, status

from autobot_shared.logging_manager import get_logger


logger = get_logger(__name__)


def actor_id(current_user: dict) -> uuid.UUID:
    """The acting user, from the session — never from the body or query."""
    raw = current_user.get("id") or current_user.get("user_id")
    return uuid.UUID(str(raw))


def bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def forbidden(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


def registry_unavailable(exc: Exception) -> HTTPException:
    """503, not 400.

    An unpopulated tool registry is an environment problem, and reporting it as
    a bad request tells the caller to fix their input when there is nothing
    wrong with it.
    """
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


async def agent_node_uuid(agent_id: str, company_id: str) -> Optional[uuid.UUID]:
    """Resolve an agent's slug to its `agent_org_nodes.id`, or ``None`` (#15905).

    `_agent_context` yields a slug (``"agent-1"``); `LLCWorkItemComment.
    author_agent_id` is a UUID. Without this the column can only be ``None`` and
    an agent's comment is stored authorless — which is not a smaller version of
    the right answer, it is the information the comment exists to carry.

    **Scoped by company, and that is load-bearing.** The slug is unique per
    company, not globally (#15812), so `WHERE agent_id = :slug` alone returns
    whichever company's row the database happens to hold and would attribute one
    company's comment to another company's agent. Nothing would look wrong: the
    query returns exactly one row.

    ``None`` has **two** causes and the caller cannot tell them apart:

    * the agent has no node — an API key can outlive its node, and a comment
      from an agent that no longer exists is still worth storing;
    * the node exists but its ``company_id`` is NULL. ``AgentOrgNode.company_id``
      is ``nullable=True`` with nothing backfilling it, so on a pre-backfill
      deployment a perfectly healthy agent resolves to ``None`` here and its
      comment is stored **authorless**. Same shape as a correct company predicate
      against a column nobody has populated (#15858, #15864).

    Storing the comment either way is deliberate — losing the comment would be
    worse than losing its author — but the second cause is a data gap, not an
    absent agent, and this docstring named only the first.

    Core `select`, not `text()`: comparing a `uuid` column to a bound string is
    dialect-fragile. PostgreSQL rejects `uuid = text` outright, and SQLite stores
    UUIDs as 32 hex characters so a dashed literal silently matches nothing —
    which reads as "this agent has no node" rather than as a broken query.
    """
    from sqlalchemy import select as _select

    from models.agent_org import AgentOrgNode
    from user_management.database import get_async_session_factory

    factory = get_async_session_factory()
    async with factory() as session:
        node = (
            await session.execute(
                _select(AgentOrgNode.id).where(
                    AgentOrgNode.agent_id == agent_id,
                    AgentOrgNode.company_id == uuid.UUID(company_id),
                )
            )
        ).scalar_one_or_none()
    return node


def agent_context(request: Request) -> tuple[str, str]:
    """Extract agent_id and company_id from middleware-injected state.

    **`company_id` is validated as a UUID here, and that is not belt-and-braces
    (#15905).** Five call sites in this file do `uuid.UUID(company_id)` against a
    UUID column, and the value is not constrained to be one:
    `LLCApiKey.company_id` is `mapped_column(String(255))`, this function checked
    truthiness only, and the auth middleware's own test asserts
    `req.state.company_id == "co-1"`. So a malformed company reached
    `uuid.UUID()` and raised `ValueError` — a 500 for something that is not a
    server fault.

    That is the defect this PR fixes for `agent_id`, on the other element of the
    same tuple. The comment on `get_next_work_item` names the class; this is the
    other instance of it, two lines down, and I committed it while writing that
    comment.

    Validated **here** rather than at the five use sites because this is where
    the value enters. A guard per site is a guard the sixth site will not have —
    and two of the five (`:544`, `:570`) predate this PR, so per-site fixing
    would have left them.

    401 rather than 422: a well-formed request carrying an auth context the auth
    layer built wrong is not the caller's error to correct. Every LLC table but
    `llc_agent_api_keys` keys company on a UUID column, so a non-UUID company
    could never match a row anyway — this reports that instead of failing later
    and elsewhere.
    """
    agent_id = getattr(request.state, "agent_id", None)
    company_id = getattr(request.state, "company_id", None)
    if not agent_id or not company_id:
        raise HTTPException(status_code=401, detail="Agent context not injected")
    try:
        uuid.UUID(str(company_id))
    except ValueError as exc:
        logger.warning("Agent context for %s carries a non-UUID company: %r", agent_id, company_id)
        raise HTTPException(status_code=401, detail="Agent context carries a malformed company") from exc
    return agent_id, company_id


async def assert_item_in_company(item_id: str, company_id: str) -> None:
    """GH#12156: 404 unless the work item belongs to the caller's company.

    KB collections are keyed by work_item_id alone, so tenant isolation must be
    enforced at the handler by verifying ownership before any KB read.
    """
    from autobot_shared.singleton_factory import lazy_singleton
    from user_management.database import get_async_session_factory

    from ..services.work_item_service import WorkItemService

    # `WorkItemService.get` does `uuid.UUID(str(work_item_id))` unguarded, and
    # `item_id` is a client-supplied body field on both callers. Without this a
    # malformed id is a `ValueError` -> 500, for a request the caller can fix.
    #
    # Third instance of the class this PR names in `get_next_work_item`'s
    # comment, found by grepping the file for the class rather than by review:
    # `run_id` had an explicit 422 two lines from `work_item_id` that had none.
    # The guard went on the input that looked dangerous, not the one that was
    # unchecked.
    try:
        uuid.UUID(str(item_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"work_item_id {item_id!r} is not a UUID") from exc

    factory = get_async_session_factory()
    async with factory() as session:
        svc = lazy_singleton(WorkItemService)()
        item = await svc.get(session, item_id)
    if item is None or str(item.company_id) != str(company_id):
        raise HTTPException(status_code=404, detail="Work item not found")
