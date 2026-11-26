# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may list a team's chat sessions (#21667).

``GET /chat/sessions?scope=team&team_id=X`` listed team X's sessions to any signed-in user. The
caller must now be a member of X, asked of the canonical ``TeamService.is_team_member``; no second
membership check lives here. An administrator passes, as for ``scope=org``. Anything that cannot be
decided (no user id, a malformed id, an unreachable database) refuses: "unknown" is never "member".
"""

import uuid
from typing import Any, Dict

from fastapi import HTTPException

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

TEAM_MEMBERSHIP_REQUIRED = "Team membership required for team-scoped listing"


async def _is_member(user_data: Dict[str, Any], team_id: str) -> bool:
    from user_management.database import db_session_context  # noqa: PLC0415 -- ORM import on use
    from user_management.services import TeamService, TenantContext  # noqa: PLC0415 -- ORM import on use

    raw_user = user_data.get("user_id") or user_data.get("id")
    user_id, tid = uuid.UUID(str(raw_user)), uuid.UUID(str(team_id))
    raw_org = user_data.get("org_id")
    context = TenantContext(org_id=uuid.UUID(str(raw_org)) if raw_org else None, user_id=user_id)
    async with db_session_context() as session:
        return await TeamService(session, context).is_team_member(tid, user_id)


async def require_team_member(user_data: Dict[str, Any], team_id: str) -> None:
    """Return when the caller is an administrator or a member of *team_id*; else raise 403."""
    if is_admin_role(user_data.get("role")):
        return
    try:
        member = await _is_member(user_data, team_id)
    except Exception as exc:  # malformed id, no user id, or the database: undecided refuses
        logger.warning("Team membership of %s could not be established: %s", user_data.get("username"), exc)
        member = False
    if not member:
        raise HTTPException(status_code=403, detail=TEAM_MEMBERSHIP_REQUIRED)
