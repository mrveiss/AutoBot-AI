# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: PROPOSE how to resolve duplicated secrets (#17850, #17038).

Endpoints:
    GET  /api/admin/secret-duplicates            duplicated groups as counts, vaults and approval ids (no secret ids)
    POST /api/admin/secret-duplicates/requests   verify every copy against its target and PROPOSE the
                                                 resolution -- creates PENDING approvals

No route removes anything. Each copy is verified (the copy that works wins); the proposal names the survivor
when exactly one verifies and asks a person to choose otherwise. Nothing runs until an admin approves it in the
Approvals inbox, and it is never auto-approved. Each call probes at most
``AUTOBOT_SECRET_DUPLICATE_MAX_GROUPS_PER_REQUEST`` groups and reports ``remaining``; a group whose proposal was
rejected stays unproposed until an admin passes ``?re_raise=true``.
The executor lives in ``services.secret_duplicate_cleanup_action``.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_secret_duplicates import (
    DuplicateGroupStatus,
    DuplicateProposal,
    DuplicateRequestResponse,
    DuplicateStatus,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from services.secret_duplicate_proposals import group_digest, pending_proposals, propose_duplicate_resolutions
from services.secret_duplicates import find_duplicate_groups
from services.secrets_maintenance import MaintenanceActor
from services.secrets_principal_resolver import ADMIN_PERMISSION

router = APIRouter(prefix="/admin", dependencies=[Depends(check_admin_permission)])


#: What the audit row of a probe read cites, before any approval exists to cite (#17850).
_REQUEST_REFERENCE = "duplicate-verification-request"


def _maintenance_actor(requester: object) -> MaintenanceActor:
    """The requesting administrator as the coordinator's maintenance principal; 403 when not a user account.

    ``check_admin_permission`` has already refused a non-administrator on this router; the coordinator checks again.
    """
    try:
        admin_id = uuid.UUID(str(requester))
    except ValueError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "The request cannot be attributed to an administrator account"
        ) from None
    return MaintenanceActor(admin_id, frozenset({ADMIN_PERMISSION}), _REQUEST_REFERENCE)


@router.get("/secret-duplicates", response_model=DuplicateStatus)
async def secret_duplicates_status(session: AsyncSession = Depends(get_db_session)) -> DuplicateStatus:
    """Read only: counts, vault references and approval ids. No secret id, name or value (#17865)."""
    groups, pending = await find_duplicate_groups(session), await pending_proposals(session)
    shown = [
        DuplicateGroupStatus(
            owner_vault=g.owner_vault,
            copy_count=len(g.secret_ids),
            approval_id=pending.get(group_digest(g.secret_ids)),
        )
        for g in groups
    ]
    return DuplicateStatus(group_count=len(shown), copy_count=sum(g.copy_count for g in shown), groups=shown)


@router.post(
    "/secret-duplicates/requests", response_model=DuplicateRequestResponse, status_code=status.HTTP_201_CREATED
)
async def propose_secret_duplicate_resolution(
    re_raise: bool = Query(False, description="Raise a group again after a rejected or revision-requested proposal"),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DuplicateRequestResponse:
    """Verify every duplicated group and PROPOSE its resolution -- a request, not an execution."""
    requester = current_user.get("id") or current_user.get("user_id")  # as the approve route reads the decider
    if not requester:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The proposal cannot be attributed to a verified user")
    actor = _maintenance_actor(requester)
    batch = await propose_duplicate_resolutions(session, str(requester), actor, re_raise=re_raise)
    if not batch.results and not batch.remaining:
        raise HTTPException(status.HTTP_409_CONFLICT, "There are no duplicated secrets")
    return DuplicateRequestResponse(
        proposals=[
            DuplicateProposal(approval_id=r.approval_id, reason=r.reason, copies=r.copies, skipped=r.skipped)
            for r in batch.results
        ],
        remaining=batch.remaining,
    )
