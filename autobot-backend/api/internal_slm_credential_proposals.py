# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Internal API: the SLM PROPOSES deleting a node's stored SSH password (#20046, #17038).

    POST /api/internal/slm/ssh-password-deletion-proposals   (X-Internal-API-Key only)

Creates one PENDING approval naming the node and the credential kind, never the value. A second call for
a node whose proposal is still pending returns that one. Nothing is deleted here: a human approves it in
the Approvals inbox, and ``services.slm_ssh_password_action`` then asks the SLM to delete it.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_slm_credential_proposals import SshPasswordDeletionProposal, SshPasswordDeletionProposalResponse
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.auth.internal_api_key import verify_internal_api_key
from autobot_shared.slm_credential_deletion import ACTION, CREDENTIAL_KIND, proposer_id
from models.approval import Approval, ApprovalStatus, ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.slm_ssh_password_action import register_ssh_password_action


async def require_internal_key(x_internal_api_key: str | None = Header(None, alias="X-Internal-API-Key")) -> None:
    """Only the SLM's service key may propose; a user session is refused."""
    if not verify_internal_api_key(x_internal_api_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "internal service key required")


# get_current_user is the recognised gate; require_internal_key narrows it to the service key alone.
router = APIRouter(prefix="/internal/slm", dependencies=[Depends(require_internal_key), Depends(get_current_user)])

# Registered at this router's import time so the executor exists before any approve().
register_ssh_password_action()


@router.post(
    "/ssh-password-deletion-proposals",
    response_model=SshPasswordDeletionProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_ssh_password_deletion(
    body: SshPasswordDeletionProposal, session: AsyncSession = Depends(get_db_session)
) -> SshPasswordDeletionProposalResponse:
    """Propose the deletion -- a request, not an execution; one pending proposal per node."""
    service = ApprovalGateService(session)
    pending = await service.list_approvals(
        status=ApprovalStatus.PENDING.value,
        agent_id=proposer_id(body.node_id),
        extra_where=(Approval.context["action"].astext == ACTION,),
        limit=1,
    )
    if pending:
        return SshPasswordDeletionProposalResponse(
            approval_id=str(pending[0].id), status=pending[0].status, created=False
        )
    approval = await service.create_approval(
        title=f"Delete the stored SSH password of node {body.node_id}",
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=(
            f"Node {body.node_id} enrolled and now uses key authentication, so its stored SSH password is no "
            "longer needed. Approving deletes the stored password for good; rejecting keeps it."
        ),
        requested_by_agent=proposer_id(body.node_id),
        context={"action": ACTION, "node_id": body.node_id, "credential_kind": CREDENTIAL_KIND},
    )
    return SshPasswordDeletionProposalResponse(approval_id=str(approval.id), status=approval.status, created=True)
