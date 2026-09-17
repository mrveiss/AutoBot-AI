# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: break-glass repair for an unreachable resource (#15779).

Endpoint:
    POST /api/admin/resource-grants/repair

Access: admin/superadmin role required (RBAC enforced via require_role
dependency). See services.resource_visibility.repair_grant for why this
grants access rather than mutating the resource's own owner/scope columns.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from services.resource_visibility import repair_grant

router = APIRouter(prefix="/admin")


class RepairGrantRequest(BaseModel):
    resource_type: str = Field(..., min_length=1, max_length=32)
    resource_id: str = Field(..., min_length=1, max_length=255)
    grantee_type: str = Field(..., pattern="^(user|group)$")
    grantee_id: str = Field(..., min_length=1, max_length=255)
    permission: str = Field(default="use", pattern="^(view|use|manage)$")


class RepairGrantResponse(BaseModel):
    id: str
    resource_type: str
    resource_id: str
    grantee_type: str
    grantee_id: str
    permission: str


@router.post("/resource-grants/repair", response_model=RepairGrantResponse, status_code=201)
async def repair_resource_grant(
    body: RepairGrantRequest,
    current_user: dict = Depends(get_current_user),
    _admin: bool = Depends(require_role("admin", "superadmin")),
    session: AsyncSession = Depends(get_db_session),
) -> RepairGrantResponse:
    """Grant access to a resource that `is_visible()` denies to everyone.

    The one in-app remedy for #15779's orphan class: an admin explicitly
    grants a user or group access, which `is_visible()` honors unconditionally
    ahead of any scope rule -- no owner or scope key on the resource itself
    needs to change.
    """
    actor_id = str(current_user.get("user_id") or current_user.get("username") or "unknown")
    row = await repair_grant(
        session,
        body.resource_type,
        body.resource_id,
        body.grantee_type,
        body.grantee_id,
        permission=body.permission,
        actor_user_id=actor_id,
    )
    return RepairGrantResponse(
        id=str(row.id),
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        grantee_type=row.grantee_type,
        grantee_id=row.grantee_id,
        permission=row.permission,
    )
