# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Preview and request the project backfill for a company's work items (#18978, #17038).

``GET`` is read-only. ``POST`` files an approval; it changes no row. A person with another seat approves it
through the approval queue, and only then does ``services.project_backfill_action`` write anything.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from api.user_management.human_decider import require_interactive_human
from llc.deps import assert_company_access, get_session
from llc.services.authz import NotAuthorisedError, require_company_admin
from llc.services.project_backfill import preview_project_backfill
from services.project_backfill_action import register_project_backfill_action
from services.project_backfill_proposal import propose_project_backfill
from user_management.services import TenantContext

from ._common import actor_id

router = APIRouter(prefix="/companies/{company_id}/project-backfill", tags=["llc-project-backfill"])
register_project_backfill_action()  # the handler exists before any approval can name it


async def _admin_preview(session: AsyncSession, company_id: uuid.UUID, user: dict, ctx: TenantContext) -> dict:
    assert_company_access(ctx, company_id)
    try:
        await require_company_admin(session, company_id, actor_id(user))
    except NotAuthorisedError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Company owner or admin required") from exc
    return await preview_project_backfill(session, company_id)


@router.get("")
async def read_preview(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """How many work items have no project and where each would go. Changes nothing."""
    return await _admin_preview(session, company_id, current_user, ctx)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def request_backfill(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """File the approval request. Nothing changes until a person approves it."""
    require_interactive_human(current_user, "project backfill request")
    preview = await _admin_preview(session, company_id, current_user, ctx)
    approval = await propose_project_backfill(
        company_id=company_id, requested_by=str(actor_id(current_user)), preview=preview
    )
    return {"approval_id": str(approval.id), "status": approval.status, "preview": preview}
