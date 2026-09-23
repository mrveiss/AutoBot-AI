# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: find and repair resources no live principal can reach (#15779, #16927).

Endpoints:
    GET  /api/admin/orphans?resource_type=...   list orphans of one type (#15779 AC4)
    POST /api/admin/orphans/repair              assign a live owner to one orphan

Access: admin/superadmin (``require_role``). A repair is a break-glass, and is
refused unless the resource is genuinely unreachable; see ``services.orphan_repair``.
Every attempt, refused or not, is audited.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_orphan_repair import OrphanListResponse, OrphanRepairRequest, OrphanRepairResponse
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from autobot_shared.principal import resolve_principal_id
from services.orphan_repair import (
    InvalidNewOwner,
    NotAnOrphan,
    OrphanRepairError,
    ResourceNotFound,
    UnknownResourceType,
    find_orphans,
    repair_orphan,
)
from services.orphan_repair_types import REPAIRERS

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

#: How each refusal is answered. A reachable resource is a conflict, not a bad request.
_STATUS = {UnknownResourceType: 400, InvalidNewOwner: 400, ResourceNotFound: 404, NotAnOrphan: 409}


def _http_error(exc: OrphanRepairError) -> HTTPException:
    status = next((code for kind, code in _STATUS.items() if isinstance(exc, kind)), 422)
    return HTTPException(status_code=status, detail={"reason": str(exc), "conditions": exc.conditions})


@router.get("/orphans", response_model=OrphanListResponse)
async def list_orphans(
    resource_type: str = Query(..., min_length=1, max_length=32),
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
) -> OrphanListResponse:
    """Orphans among the first *limit* resources of a type, so they surface before a user trips on one."""
    try:
        orphans = await find_orphans(session, REPAIRERS, resource_type, limit)
    except OrphanRepairError as exc:
        raise _http_error(exc) from exc
    return OrphanListResponse(resource_type=resource_type, orphans=orphans)


@router.post("/orphans/repair", response_model=OrphanRepairResponse, status_code=201)
async def repair_orphan_resource(
    body: OrphanRepairRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrphanRepairResponse:
    """Assign a live owner to a resource no live principal can reach. Refused (409) if any can."""
    actor = resolve_principal_id(current_user) or str(current_user.get("username") or "unknown")
    try:
        result = await repair_orphan(
            session, REPAIRERS, body.resource_type, body.resource_id, body.new_owner_id, actor_user_id=actor
        )
    except OrphanRepairError as exc:
        raise _http_error(exc) from exc
    return OrphanRepairResponse(resource_type=body.resource_type, resource_id=body.resource_id, **result)
