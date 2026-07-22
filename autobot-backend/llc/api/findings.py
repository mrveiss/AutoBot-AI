# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC findings API — scan / proposals / promote / dismiss (#11271).

Routes (all served under /api/llc via the parent router):
  POST /projects/{project_id}/findings/scan
  GET  /projects/{project_id}/findings/proposals
  POST /findings/proposals/{proposal_id}/promote
  POST /findings/proposals/{proposal_id}/dismiss
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import get_session, load_owned_project as _load_owned_project
from llc.models.finding_proposal import LLCFindingProposal
from llc.services.finding_proposal_service import (
    FindingsDisabledError,
    ProposalStateError,
    dismiss,
    promote,
    scan,
)
from llc.services.findings_policy import get_findings_policy
from user_management.services import TenantContext

logger = get_logger(__name__)
router = APIRouter(tags=["llc-findings"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class FindingProposalResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    project_id: uuid.UUID
    source_id: str
    finding_key: str
    finding_type: str
    severity: str
    file_path: str
    line_number: Optional[int]
    description: str
    suggestion: Optional[str]
    verdict_is_real: Optional[bool]
    verdict_confidence: Optional[float]
    verdict_rationale: Optional[str]
    status: str
    work_item_id: Optional[uuid.UUID]
    dismiss_reason: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class DismissRequest(BaseModel):
    reason: str


# ---------------------------------------------------------------------------
# IDOR guards
# ---------------------------------------------------------------------------


async def _load_owned_proposal(proposal_id: uuid.UUID, session: AsyncSession, ctx: TenantContext) -> LLCFindingProposal:
    """Load proposal by id; 404 when missing or owned by a different org."""
    result = await session.execute(select(LLCFindingProposal).where(LLCFindingProposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if proposal is None or str(proposal.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/projects/{project_id}/findings/scan")
async def scan_findings(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Scan a project's linked repo for findings and queue real ones as proposals."""
    policy = await get_findings_policy()
    if not policy.enabled:
        raise HTTPException(status_code=403, detail="Findings feature is disabled")

    project = await _load_owned_project(project_id, session, ctx)
    if not project.code_source_id:
        raise HTTPException(status_code=409, detail="Project has no linked code source")

    try:
        return await scan(project, session)
    except FindingsDisabledError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        # The linked source was deleted / left "ready" between the check above and
        # the scan (gather/clone-path resolution) — treat as a 409, not a 500.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects/{project_id}/findings/proposals", response_model=List[FindingProposalResponse])
async def list_proposals(
    project_id: uuid.UUID,
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[LLCFindingProposal]:
    """List finding proposals for a project, optionally filtered by status."""
    await _load_owned_project(project_id, session, ctx)
    stmt = select(LLCFindingProposal).where(LLCFindingProposal.project_id == project_id)
    if status is not None:
        stmt = stmt.where(LLCFindingProposal.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("/findings/proposals/{proposal_id}/promote")
async def promote_proposal(
    proposal_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Promote a pending proposal to a work item (or gate on approval)."""
    proposal = await _load_owned_proposal(proposal_id, session, ctx)
    actor_id = uuid.UUID(str(current_user.get("id") or current_user.get("user_id")))
    try:
        result = await promote(proposal, session, actor_id)
    except ProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(result, dict):
        return result
    # Return a summary of the created work item.
    return {
        "result": "promoted",
        "work_item_id": str(result.id),
        "identifier": getattr(result, "identifier", None),
        "title": getattr(result, "title", None),
    }


@router.post("/findings/proposals/{proposal_id}/dismiss")
async def dismiss_proposal(
    proposal_id: uuid.UUID,
    body: DismissRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    """Dismiss a pending proposal with a reason."""
    proposal = await _load_owned_proposal(proposal_id, session, ctx)
    try:
        await dismiss(proposal, session, body.reason)
    except ProposalStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"result": "dismissed"}
