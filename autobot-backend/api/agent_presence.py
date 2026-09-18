# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read access to the live agent-presence registry (#16947, #16965 review).

The registry itself (`protocols/agent_presence.py`) is process-local and has
no route of its own -- `initialization/lifespan.py`'s background sync is the
only writer. This is the one reader: scoped to the caller's own tenant plus
shared infrastructure, exactly what `AgentPresenceRegistry.list_live()`
already restricts to, so this route adds no authorization logic of its own
beyond resolving *which* tenant the caller is.

Not `api/presence_ws.py` -- that is the unrelated collaborative-UI presence
WebSocket (who is viewing a page), not this agent-kind registry.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from api.user_management.dependencies import get_current_user, require_org_context
from protocols.agent_presence import get_presence_registry
from user_management.services import TenantContext

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/agents/presence", response_model=List[Dict[str, Any]])
async def list_agent_presence(
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """Every agent visible to the caller: its own tenant's, plus shared.

    Tenant comes from the verified JWT/session context (`require_org_context`),
    never a request parameter -- a caller cannot ask to see another tenant's
    agents by passing one in.
    """
    entries = get_presence_registry().list_live(str(ctx.org_id) if ctx.org_id else None)
    return [
        {
            "kind": entry.kind.value,
            "tenant_id": entry.tenant_id,
            "name": entry.name,
            "busy": entry.busy,
            "detail": entry.detail,
            "last_seen": entry.last_seen,
        }
        for entry in entries
    ]
