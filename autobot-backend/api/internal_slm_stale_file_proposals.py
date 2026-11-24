# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Internal API: stale code-sync files are PROPOSED for removal and claimed once a human approved (#22033, #17038).

    POST /api/internal/slm/stale-file-proposals                    (X-Internal-API-Key only)
    POST /api/internal/slm/stale-file-approvals/{id}/claim         (X-Internal-API-Key only)

A proposal lists the files of ONE old sync location on ONE node (path, size, age, never contents); a second
call for a location whose proposal is still pending returns that one. Nothing is removed here: a human
approves it in the Approvals inbox, the backend's executor calls the SLM, and the SLM claims the approval
(verified as a human's, for this node, unused -- then spent) before it removes anything. The proposal's audit
row is durable and written FIRST: a proposal whose row cannot be written creates nothing (503), and a claim
whose row cannot be written spends nothing (503).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_slm_stale_file_proposals import (
    StaleFileClaim,
    StaleFileClaimResponse,
    StaleFileEntry,
    StaleFileProposal,
    StaleFileProposalResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_service_opt_in import service_opt_in
from autobot_shared.auth.internal_api_key import require_internal_api_key
from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_credential_actions import SPLIT_DEPLOYMENT_MESSAGE, is_split_without_tls
from autobot_shared.slm_stale_file_actions import LOCATION_KEY, STALE_SYNC_FILES_CLEANUP, location
from models.approval import Approval, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.audit.taxonomy import AuditAction
from services.audit_logger import audit_log
from services.kb_cleanup_proposals import create_proposal_once, record_cleanup_proposed
from services.slm_credential_claim import ClaimNotRecorded, ClaimRefused, claim_approval
from services.slm_stale_file_texts import stale_files_proposal_text
from services.slm_stale_sync_files_action import register_stale_sync_files_action

logger = get_logger(__name__)

#: The caller named on the service-key admission audit row (#16333).
SLM_CALLER = "slm-stale-file-cleanup"
_NOT_RECORDED = "the step could not be recorded; try again"

# get_current_user is the recognised gate; require_internal_api_key narrows it to the service key alone. The
# SLM's calls carry that key and no user, so each handler names its caller with service_opt_in (#16333).
router = APIRouter(prefix="/internal/slm", dependencies=[Depends(require_internal_api_key), Depends(get_current_user)])

# Registered at this router's import time so the executor exists before any approve().
register_stale_sync_files_action()


def _context(body: StaleFileProposal) -> dict:
    """The approval's frozen context: what a human reviewed is all the executor and the claim can act on."""
    return {
        "action": STALE_SYNC_FILES_CLEANUP.name,
        "node_id": body.node_id,
        "credential_kind": STALE_SYNC_FILES_CLEANUP.credential_kind,
        LOCATION_KEY: location(body.node_id, body.old_target),
        "old_target": body.old_target,
        "commit": body.commit,
        "total_found": body.total_found,
        "files": [entry.model_dump(mode="json") for entry in body.files],
    }


async def _create_approval(
    service: ApprovalGateService, body: StaleFileProposal, approval_id: uuid.UUID, current_user: dict
) -> Approval:
    """The audit row first (no row, no proposal: 503), then the pending approval it names."""
    await record_cleanup_proposed(
        approval_id,
        current_user,
        operation=AuditAction.CODE_SYNC_STALE_FILES_CLEANUP,
        resource=f"node:{body.node_id}",
    )
    title, description = stale_files_proposal_text(
        body.node_id, body.old_target, [entry.model_dump() for entry in body.files], body.total_found
    )
    return await service.create_approval(
        title=title,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=description,
        requested_by_agent=STALE_SYNC_FILES_CLEANUP.proposer_id(body.node_id),
        context=_context(body),
        approval_id=approval_id,
    )


def _response(approval: Approval, created: bool) -> StaleFileProposalResponse:
    """The stored approval's own counts: what the reviewer opens, not what this request asked for."""
    context = approval.context or {}
    files = context.get("files") or []
    return StaleFileProposalResponse(
        approval_id=str(approval.id),
        status=approval.status,
        created=created,
        proposed=len(files),
        total_found=int(context.get("total_found", len(files))),
    )


@router.post("/stale-file-proposals", response_model=StaleFileProposalResponse, status_code=status.HTTP_201_CREATED)
@service_opt_in(SLM_CALLER)
async def propose_stale_file_cleanup(
    body: StaleFileProposal,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StaleFileProposalResponse:
    """Propose removing the files -- a request, not an execution; one open proposal per location per node."""
    if is_split_without_tls():  # #20899: the approved removal could not run, so do not offer it
        raise HTTPException(status.HTTP_409_CONFLICT, SPLIT_DEPLOYMENT_MESSAGE)
    service = ApprovalGateService(session)
    made: list[uuid.UUID] = []

    async def create(approval_id: uuid.UUID) -> Approval:
        made.append(approval_id)
        return await _create_approval(service, body, approval_id, current_user)

    approval = await create_proposal_once(
        service,
        STALE_SYNC_FILES_CLEANUP.name,
        LOCATION_KEY,
        location(body.node_id, body.old_target),
        create,
        current_user=current_user,
        resource=f"node:{body.node_id}",
    )
    return _response(approval, created=approval.id in made)


async def _record_claim(approval: Approval) -> bool:
    """The durable row that must exist before a claim spends the approval."""
    return await audit_log(
        AuditAction.CODE_SYNC_STALE_FILES_CLEANUP,
        result="success",
        durable=True,
        user_id=approval.decided_by_user,
        resource=f"node:{(approval.context or {}).get('node_id')}",
        details={"approval_id": str(approval.id), "phase": "claimed"},
    )


@router.post("/stale-file-approvals/{approval_id}/claim", response_model=StaleFileClaimResponse)
@service_opt_in(SLM_CALLER)
async def claim_stale_file_approval(
    approval_id: uuid.UUID, body: StaleFileClaim, session: AsyncSession = Depends(get_db_session)
) -> StaleFileClaimResponse:
    """The SLM's last check: a human approved THESE files for this node, unused -- now spent; they come back."""
    try:
        approval = await claim_approval(session, approval_id, STALE_SYNC_FILES_CLEANUP, body.node_id, _record_claim)
    except ClaimRefused as refusal:
        logger.warning("Stale-file claim refused for approval %s: %s", approval_id, refusal)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "the approval does not authorize this removal")
    except ClaimNotRecorded:
        logger.error("Stale-file claim for approval %s not spent: its audit row was not written", approval_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_RECORDED)
    context = approval.context or {}
    return StaleFileClaimResponse(
        approval_id=str(approval_id),
        node_id=body.node_id,
        old_target=context["old_target"],
        files=[StaleFileEntry(**entry) for entry in context["files"]],
    )
