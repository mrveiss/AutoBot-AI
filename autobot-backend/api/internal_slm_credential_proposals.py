# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Internal API: a stored credential change is PROPOSED, claimed once approved, and reported (#20046, #20750, #17038).

    POST /api/internal/slm/credential-proposals                      (X-Internal-API-Key only)
    POST /api/internal/slm/credential-approvals/{id}/claim           (X-Internal-API-Key only)
    POST /api/internal/slm/credential-approvals/{id}/outcome         (X-Internal-API-Key only)

One route set for every action in ``autobot_shared.slm_credential_actions.ACTIONS``. A proposal names
the action and the node, never a value; a second call for a node whose approval is still open (pending,
or approved and unused) returns that one. Nothing changes here: a human approves it in the Approvals
inbox, the applying side claims it (verified, then spent once), applies the change, and reports.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_slm_credential_proposals import (
    CredentialClaim,
    CredentialClaimResponse,
    CredentialOutcome,
    CredentialProposal,
    CredentialProposalResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.auth.internal_api_key import require_internal_api_key
from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_credential_actions import ACTIONS, INTERNAL_KEY_REALIGN, CredentialAction
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.slm_credential_claim import (
    CONSUMED_KEY,
    ClaimRefused,
    OutcomeRefused,
    claim_approval,
    clean_detail,
    record_outcome,
)
from services.slm_credential_texts import proposal_text, record_realign_step
from services.slm_internal_key_realign_action import register_internal_key_realign_action
from services.slm_ssh_password_action import register_ssh_password_action

logger = get_logger(__name__)

# get_current_user is the recognised gate; require_internal_api_key narrows it to the service key alone.
router = APIRouter(prefix="/internal/slm", dependencies=[Depends(require_internal_api_key), Depends(get_current_user)])

# Registered at this router's import time so the executors exist before any approve().
register_ssh_password_action()
register_internal_key_realign_action()


async def _open_approval(service: ApprovalGateService, action: CredentialAction, node_id: str) -> Approval | None:
    """The node's approval for *action* that can still be acted on: pending, or (where the action reuses
    one) approved and not yet spent."""
    states = [ApprovalStatus.PENDING.value] + ([ApprovalStatus.APPROVED.value] if action.reuse_approved else [])
    for state in states:
        found = await service.list_approvals(
            status=state,
            agent_id=action.proposer_id(node_id),
            extra_where=(
                Approval.context["action"].astext == action.name,
                Approval.context[CONSUMED_KEY].astext.is_(None),
            ),
            limit=1,
        )
        if found:
            return found[0]
    return None


@router.post("/credential-proposals", response_model=CredentialProposalResponse, status_code=status.HTTP_201_CREATED)
async def propose_credential_change(
    body: CredentialProposal, session: AsyncSession = Depends(get_db_session)
) -> CredentialProposalResponse:
    """Propose the change -- a request, not an execution; one open proposal per node and action."""
    action = ACTIONS[body.action]
    service = ApprovalGateService(session)
    if existing := await _open_approval(service, action, body.node_id):
        return CredentialProposalResponse(approval_id=str(existing.id), status=existing.status, created=False)
    title, description = proposal_text(action, body.node_id)
    approval = await service.create_approval(
        title=title,
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=description,
        requested_by_agent=action.proposer_id(body.node_id),
        context={"action": action.name, "node_id": body.node_id, "credential_kind": action.credential_kind},
    )
    if action is INTERNAL_KEY_REALIGN:
        await record_realign_step("proposed", approval, "success")
    return CredentialProposalResponse(approval_id=str(approval.id), status=approval.status, created=True)


@router.post("/credential-approvals/{approval_id}/claim", response_model=CredentialClaimResponse)
async def claim_credential_approval(
    approval_id: uuid.UUID, body: CredentialClaim, session: AsyncSession = Depends(get_db_session)
) -> CredentialClaimResponse:
    """The applying side's last check: this approval is a human's, for this action and node, and unused -- now spent."""
    action = ACTIONS[body.action]
    try:
        approval = await claim_approval(session, approval_id, action, body.node_id)
    except ClaimRefused as refusal:
        logger.warning("Credential claim refused for approval %s (%s): %s", approval_id, action.name, refusal)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "the approval does not authorize this change")
    if action is INTERNAL_KEY_REALIGN:
        await record_realign_step("claimed", approval, "success")
    return CredentialClaimResponse(approval_id=str(approval_id), node_id=body.node_id)


@router.post("/credential-approvals/{approval_id}/outcome", status_code=status.HTTP_204_NO_CONTENT)
async def report_credential_outcome(
    approval_id: uuid.UUID, body: CredentialOutcome, session: AsyncSession = Depends(get_db_session)
) -> None:
    """Record how applying a CLAIMED approval went, ONCE: an audit entry and a comment on the approval.

    The first terminal report wins and a second is refused (409), so an "applied" record can't be
    forged or overwritten after the fact. The reported detail is cleaned and capped before it is kept.
    """
    action = ACTIONS[body.action]
    try:
        approval = await record_outcome(session, approval_id, action, body.node_id, body.result)
    except OutcomeRefused as refusal:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refusal))
    applied = body.result == "applied"
    detail = clean_detail(body.detail)
    if action is INTERNAL_KEY_REALIGN:
        await record_realign_step(
            "applied" if applied else "apply_failed", approval, "success" if applied else "failed", detail=detail
        )
    note = "Applied." if applied else f"Applying it failed: {detail or 'no detail given'}"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=note))
    await session.commit()
