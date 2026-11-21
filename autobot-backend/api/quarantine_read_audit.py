# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin routes that read research-quarantined facts through the audited opt-out (#19163).

The raw ChromaDB explorer and the knowledge lint are the two owner-approved readers (ruling
2026-10-22) allowed to see quarantined facts. They never read unaudited: each calls
:func:`audit_admin_quarantine_read`, which resolves who is asking and writes the entry through
``knowledge.quarantine.audit_quarantine_read`` -- the one audit path.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from fastapi import HTTPException, Request

from auth_middleware import resolve_human_user
from autobot_shared.logging_manager import get_logger
from knowledge.quarantine import audit_quarantine_read, is_quarantined

logger = get_logger(__name__)

#: Actor recorded when the caller authenticated with the internal service key (no human user).
INTERNAL_SERVICE_ACTOR = "internal-service"


async def request_actor(request: Request) -> str:
    """Who the admin request is: the human's username/id, else the internal service key's holder.

    The request is required: an absent one must not read as an anonymous internal service (#19163).
    """
    user = await resolve_human_user(request)
    if not user:
        return INTERNAL_SERVICE_ACTOR
    return str(user.get("username") or user.get("user_id") or user.get("id") or INTERNAL_SERVICE_ACTOR)


async def request_person(request: Request) -> str:
    """The named person acting; the internal service key is refused, so no agent can act with it (#17038)."""
    actor = await request_actor(request)
    if actor == INTERNAL_SERVICE_ACTOR:
        raise HTTPException(status_code=403, detail="A person must do this: the service key cannot.")
    return actor


def quarantined_row_ids(ids: Iterable[str], metadatas: Iterable[Mapping[str, Any] | None]) -> list[str]:
    """The ids whose metadata marks them research-quarantined (rows pair ids with metadatas)."""
    return [i for i, md in zip(ids, metadatas) if md and is_quarantined({"metadata": md})]


async def audit_admin_quarantine_read(request: Request, surface: str, ids: list[str]) -> bool:
    """Write the audit entry for an admin read that returned quarantined rows."""
    return await audit_quarantine_read(await request_actor(request), surface, ids)
