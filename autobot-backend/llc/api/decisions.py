# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company decision log API routes (GH#8243).

Routes (under /llc/companies/{company_id}/decisions):
  GET /search?q=  — RAG search over the company decisions KB
  GET /           — list decisions (paginated, filterable by type and date)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.user_management.dependencies import get_current_user, require_org_context
from user_management.services import TenantContext

from ..kb.decision_log import DecisionLogReader

router = APIRouter()
_reader = DecisionLogReader()


def _assert_company_match(ctx: TenantContext, company_id: str) -> None:
    """Reject cross-tenant access to a company-scoped decision request (GH#12148).

    404 (not 403) so a cross-tenant caller can't distinguish "not my company"
    from "doesn't exist" — matches goals.py/budget.py (GH#12136). Platform
    admins are exempt.
    """
    if company_id != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=404, detail="Company not found")


@router.get("/companies/{company_id}/decisions/search")
async def search_decisions(
    company_id: str,
    q: str = Query(..., description="Free-text search query"),
    n: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """RAG search over the company decisions knowledge base.

    Returns ranked results with text, metadata, and similarity distance.
    """
    _assert_company_match(ctx, company_id)
    try:
        cid = uuid.UUID(company_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid company_id UUID")

    results = await _reader.search(company_id=cid, query=q, n_results=n)
    return results


@router.get("/companies/{company_id}/decisions")
async def list_decisions(
    company_id: str,
    approval_type: Optional[str] = Query(None, description="Filter by approval type"),
    since: Optional[datetime] = Query(None, description="Filter decisions after this timestamp (ISO 8601)"),
    until: Optional[datetime] = Query(None, description="Filter decisions before this timestamp (ISO 8601)"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """List board decisions for a company, newest-first.

    Filterable by approval type and date range.
    """
    _assert_company_match(ctx, company_id)
    try:
        cid = uuid.UUID(company_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid company_id UUID")

    results = await _reader.list_decisions(
        company_id=cid,
        approval_type=approval_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return results


__all__ = ["router"]
