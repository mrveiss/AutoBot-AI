# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Work-item hierarchy rules and the read-only violation report (#20936, #18978).

``GET /work-items/hierarchy-rules`` serves the parent-type rule table; ``GET /work-items/hierarchy-violations``
returns the rows that already break it (company owners/admins and platform admins only). Neither writes.

This router is included BEFORE ``work_items.router`` (see ``api/__init__.py``): its literal paths would otherwise
be swallowed by that router's ``/{work_item_id}`` capture.
"""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import assert_company_access, get_session
from user_management.services import TenantContext

from ..services.authz import NotAuthorisedError, require_company_admin_unless_platform
from ..services.work_item_hierarchy import (
    ALLOWED_PARENT_TYPES,
    PROJECT_REQUIRED_TYPES,
    find_hierarchy_violations,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/work-items", tags=["llc-work-items"])


class HierarchyRule(BaseModel):
    type: str
    allowed_parent_types: List[str]
    project_required: bool


class HierarchyRulesResponse(BaseModel):
    rules: List[HierarchyRule]


class HierarchyViolationRow(BaseModel):
    id: str
    identifier: str
    reason: str


class HierarchyViolationsResponse(BaseModel):
    violations: List[HierarchyViolationRow]
    count: int


def hierarchy_rules() -> HierarchyRulesResponse:
    """The rule table as data, straight from the constants the writes are checked against."""
    return HierarchyRulesResponse(
        rules=[
            HierarchyRule(
                type=kind.value,
                allowed_parent_types=sorted(p.value for p in parents),
                project_required=kind in PROJECT_REQUIRED_TYPES,
            )
            for kind, parents in ALLOWED_PARENT_TYPES.items()
        ]
    )


@router.get("/hierarchy-rules", response_model=HierarchyRulesResponse)
async def get_hierarchy_rules(
    company_id: str = Query(...),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> HierarchyRulesResponse:
    assert_company_access(ctx, company_id)
    return hierarchy_rules()


@router.get("/hierarchy-violations", response_model=HierarchyViolationsResponse)
async def get_hierarchy_violations(
    company_id: str = Query(...),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> HierarchyViolationsResponse:
    assert_company_access(ctx, company_id)
    try:
        await require_company_admin_unless_platform(
            session, uuid.UUID(str(company_id)), ctx.user_id, platform_admin=ctx.is_platform_admin
        )
    except NotAuthorisedError as exc:
        logger.warning("Refused hierarchy-violations report for company %s: %s", company_id, exc)
        raise HTTPException(status_code=403, detail="Only a company owner or admin may read the violation report")
    rows = await find_hierarchy_violations(session, company_id)
    return HierarchyViolationsResponse(violations=[HierarchyViolationRow(**r) for r in rows], count=len(rows))
