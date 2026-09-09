# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read the live work-claim table: who is working where (#15949).

The recovery half of the projection. A client that was disconnected when a claim
was acquired cannot learn it from the event it missed, so the same fact is
readable here -- `EVENT_STATE_DOCTRINE.md` principle 2, "state over
notification".

Read-only by design. Claims are acquired and released through
`autobot_shared.coordination.work_claims`, by the agent doing the work, holding
the task identity that owns them. An HTTP endpoint that could release another
agent's claim would make every claim advisory against anyone with a session
cookie, which is a coordination bug wearing an API.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.user_management.dependencies import get_current_user
from autobot_shared.coordination.work_claims import ScopeError
from autobot_shared.logging_manager import get_logger
from services.claim_projection import claim_table

logger = get_logger(__name__)

# Authenticated like its neighbours in `_get_agent_routers`: the table names
# which agent is doing what, which is operational detail about the running
# system rather than public information.
router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/claims")
async def get_claims(
    agent_id: Optional[str] = Query(None, description="Only claims held by this agent"),
    scope: Optional[str] = Query(None, description="Only claims at or under this scope, segment-aligned"),
    kind: Optional[str] = Query(None, description="Only claims of this scope kind"),
) -> dict[str, Any]:
    """The live claim table, optionally filtered.

    A malformed `scope` or unknown `kind` is the caller's error and is reported
    as 400 rather than silently returning everything -- a filter that fails open
    would tell an operator "nothing holds this" when the truth is "that question
    was not understood".
    """
    try:
        claims = await claim_table(agent_id=agent_id, scope_prefix=scope, kind=kind)
    except ScopeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"claims": claims, "count": len(claims)}
