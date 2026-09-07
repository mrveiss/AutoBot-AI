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

from fastapi import HTTPException, status


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

    ``None`` when the agent has no node — an API key can outlive its node, and a
    comment from an agent that no longer exists is still a comment worth storing.

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
