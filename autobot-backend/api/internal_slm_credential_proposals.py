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

Each realign step's audit row is durable and written FIRST: a proposal whose row cannot be written
creates nothing (503), a claim whose row cannot be written spends nothing (503), and an outcome whose row
cannot be written is not stamped (503), so the report can be retried. A run that dies between the claim
and the outcome leaves an approval that is spent with no outcome; it is never reused, so the next update
proposes a fresh one and needs a NEW human decision.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
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
from auth_service_opt_in import service_opt_in
from autobot_shared.auth.internal_api_key import require_internal_api_key
from autobot_shared.logging_manager import get_logger
from autobot_shared.slm_credential_actions import (
    ACTIONS,
    INTERNAL_KEY_REALIGN,
    SPLIT_DEPLOYMENT_MESSAGE,
    SSH_PASSWORD_DELETE,
    CredentialAction,
    is_split_without_tls,
)
from models.approval import Approval, ApprovalComment, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.slm_credential_claim import (
    CONSUMED_KEY,
    ClaimNotRecorded,
    ClaimRefused,
    OutcomeRefused,
    claim_approval,
    clean_detail,
    record_outcome,
)
from services.slm_credential_texts import (
    proposal_text,
    record_realign_proposal,
    record_realign_proposal_failed,
    record_realign_step,
)
from services.slm_internal_key_realign_action import register_internal_key_realign_action
from services.slm_ssh_password_action import register_ssh_password_action

logger = get_logger(__name__)

#: The caller named on the service-key admission audit row (#16333).
SLM_CALLER = "slm-ssh-password-deletion"

# get_current_user is the recognised gate; require_internal_api_key narrows it to the service key alone.
# The SLM's and the updater's calls carry that key and no user, so each handler names its caller with
# service_opt_in (#16333); without it get_current_user refuses the key and nothing could be proposed or claimed.
_NOT_RECORDED = "the step could not be recorded; try again"

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


def _claim_recorder(action: CredentialAction):
    """The audit write that must succeed before a claim spends the approval; None where the action has none."""
    if action is not INTERNAL_KEY_REALIGN:
        return None
    return lambda approval: record_realign_step("claimed", approval, "success")


async def _create_proposal(
    service: ApprovalGateService,
    action: CredentialAction,
    body: CredentialProposal,
    approval_id: uuid.UUID,
    proposer: str,
) -> Approval:
    """Create the approval; a realign whose "proposed" row exists but whose approval cannot be made is compensated."""
    title, description = proposal_text(action, body.node_id)
    try:
        return await service.create_approval(
            title=title,
            approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
            description=description,
            requested_by_agent=proposer,
            context={"action": action.name, "node_id": body.node_id, "credential_kind": action.credential_kind},
            approval_id=approval_id,
        )
    except Exception as exc:
        if action is not INTERNAL_KEY_REALIGN:
            raise
        await _record_proposal_failed(approval_id, body.node_id, proposer, exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_RECORDED) from exc


async def _record_proposal_failed(approval_id: uuid.UUID, node_id: str, proposer: str, exc: Exception) -> None:
    """The compensating row; if it cannot be written that is logged loudly, never swallowed."""
    logger.error("Credential proposal %s: approval creation failed (%s)", approval_id, type(exc).__name__)
    try:
        written = await record_realign_proposal_failed(approval_id, node_id, proposer, exc)
    except Exception:
        written = False
        logger.exception("Credential proposal %s: the proposal_failed audit write raised", approval_id)
    if not written:
        logger.error("Credential proposal %s: the 'proposed' audit row has NO compensating row", approval_id)


@router.post("/credential-proposals", response_model=CredentialProposalResponse, status_code=status.HTTP_201_CREATED)
@service_opt_in(SLM_CALLER)
async def propose_credential_change(
    body: CredentialProposal, session: AsyncSession = Depends(get_db_session)
) -> CredentialProposalResponse:
    """Propose the change -- a request, not an execution; one open proposal per node and action.

    A stored-password deletion is refused (409, clear message) on a split deployment without SLM TLS (#20899).
    """
    action = ACTIONS[body.action]
    if action is SSH_PASSWORD_DELETE and is_split_without_tls():
        raise HTTPException(status.HTTP_409_CONFLICT, SPLIT_DEPLOYMENT_MESSAGE)
    service = ApprovalGateService(session)
    if existing := await _open_approval(service, action, body.node_id):
        return CredentialProposalResponse(approval_id=str(existing.id), status=existing.status, created=False)
    approval_id = uuid.uuid4()
    proposer = action.proposer_id(body.node_id)
    if action is INTERNAL_KEY_REALIGN and not await record_realign_proposal(approval_id, body.node_id, proposer):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_RECORDED)  # no row, so no proposal
    try:
        approval = await _create_proposal(service, action, body, approval_id, proposer)
    except IntegrityError:  # uq_approvals_pending_ssh_password_deletion: a concurrent request won
        await session.rollback()
        winner = await _open_approval(service, action, body.node_id)
        if winner is None:
            raise
        return CredentialProposalResponse(approval_id=str(winner.id), status=winner.status, created=False)
    return CredentialProposalResponse(approval_id=str(approval.id), status=approval.status, created=True)


@router.post("/credential-approvals/{approval_id}/claim", response_model=CredentialClaimResponse)
@service_opt_in(SLM_CALLER)
async def claim_credential_approval(
    approval_id: uuid.UUID, body: CredentialClaim, session: AsyncSession = Depends(get_db_session)
) -> CredentialClaimResponse:
    """The applying side's last check: this approval is a human's, for this action and node, and unused -- now spent."""
    action = ACTIONS[body.action]
    try:
        await claim_approval(session, approval_id, action, body.node_id, _claim_recorder(action))
    except ClaimRefused as refusal:
        logger.warning("Credential claim refused for approval %s (%s): %s", approval_id, action.name, refusal)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "the approval does not authorize this change")
    except ClaimNotRecorded:
        logger.error("Credential claim for approval %s not spent: its audit row was not written", approval_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_RECORDED)
    return CredentialClaimResponse(approval_id=str(approval_id), node_id=body.node_id)


@router.post("/credential-approvals/{approval_id}/outcome", status_code=status.HTTP_204_NO_CONTENT)
@service_opt_in(SLM_CALLER)
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
    if action is INTERNAL_KEY_REALIGN and not await record_realign_step(
        "applied" if applied else "apply_failed", approval, "success" if applied else "failed", detail=detail
    ):
        await session.rollback()  # the outcome is not stamped, so the applying side can report it again
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NOT_RECORDED)
    note = "Applied." if applied else f"Applying it failed: {detail or 'no detail given'}"
    session.add(ApprovalComment(approval_id=approval.id, author="system", author_type="system", body=note))
    await session.commit()
