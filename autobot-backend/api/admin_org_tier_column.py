# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: PROPOSE dropping ``organizations.subscription_tier`` (#19997).

Endpoints:
    GET  /api/admin/org-tier-column           whether this database still holds the column
    POST /api/admin/org-tier-column/requests  PROPOSE the drop -- creates a PENDING approval

Neither route changes the schema. Nothing runs until a human approves it in the Approvals inbox, and
it is never auto-approved (#17038). The executor lives in ``services.org_tier_column_action``.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_org_tier_column import OrgTierColumnRequestResponse, OrgTierColumnStatus
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from models.approval import ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.org_tier_column_action import ACTION, column_present, register_tier_column_action

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

# Registered at this router's import time so the executor exists before any approve().
register_tier_column_action()


@router.get("/org-tier-column", response_model=OrgTierColumnStatus)
async def org_tier_column_status(session: AsyncSession = Depends(get_db_session)) -> OrgTierColumnStatus:
    """Read only: whether there is anything to propose."""
    return OrgTierColumnStatus(present=await column_present(session))


@router.post(
    "/org-tier-column/requests", response_model=OrgTierColumnRequestResponse, status_code=status.HTTP_201_CREATED
)
async def propose_org_tier_column_drop(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrgTierColumnRequestResponse:
    """Propose the drop -- a request, not an execution. Refused when the column is already gone."""
    requester = current_user.get("user_id")
    if not requester:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The proposal cannot be attributed to a verified user")
    if not await column_present(session):
        raise HTTPException(status.HTTP_409_CONFLICT, "organizations.subscription_tier is not in this database")
    approval = await ApprovalGateService(session).create_approval(
        title="Drop the unused organizations.subscription_tier column",
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=(
            "AutoBot has no paid tiers and nothing reads this column (#19984). Approving deletes every stored value "
            "in it for good: back up the database first if you may want them."
        ),
        requested_by_agent=f"org-tier-column:{requester}",
        context={"action": ACTION},
    )
    return OrgTierColumnRequestResponse(approval_id=str(approval.id), status=approval.status, action=ACTION)
