# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: list orphan-storage candidates across every registered detector (#17038, #17039).

Endpoints:
    GET  /api/admin/orphan-storage                    preview candidates -- read-only
    POST /api/admin/orphan-storage/deletion-requests  PROPOSE one deletion

Access: admin/superadmin (``require_role``). This is preview only, on purpose:
deletion is never exposed as a bare admin-gated route here, because the owner's
rule requires every removal to go through a human-approved review queue
(#17043). The POST above is that proposal, and it is the only thing this
module gained: it creates a PENDING approval and returns. It deletes nothing,
it cannot approve anything, and no argument to it reaches ``delete_candidate``
-- that is still reachable only from the post-approval executor, after a human
decides (#17038 rule 1).

#17315: until that route existed, the chain had a detector and an executor and
no way to start it. ``orphan_storage_delete`` was registered, unit-tested, and
unreachable in production -- an admin could list candidates and could never
propose one, so the "always-available review queue" had no entry point for the
one action that implements the rule.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.codebase_analytics.orphan_clone_detector import register as register_code_source_clone_detector
from api.schemas_orphan_storage import (
    OrphanStorageCandidateResponse,
    OrphanStorageDeletionRequest,
    OrphanStorageDeletionRequestResponse,
    OrphanStorageListResponse,
    OrphanStorageProviderStatusResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from auth_rbac import require_role
from models.approval import ApprovalType
from services.approval_gate_service import ApprovalGateService
from services.orphan_storage import list_all_candidates, registered_providers
from services.orphan_storage_cleanup_action import ACTION as ORPHAN_STORAGE_DELETE
from services.orphan_storage_cleanup_action import register as register_orphan_storage_cleanup_action

router = APIRouter(prefix="/admin", dependencies=[Depends(require_role("admin", "superadmin"))])

# Registered here, at this router's own import time (once, at app startup),
# rather than as a side effect of importing orphan_clone_detector itself --
# so a test that imports that module for its functions doesn't also mutate
# the global registry. register_detector() is idempotent regardless.
register_code_source_clone_detector()

# Same reasoning: the approved-cleanup executor is registered at import time,
# not lazily -- it must be wired before any approve() call can reach it, and
# both registries are idempotent to re-registration.
register_orphan_storage_cleanup_action()


@router.get("/orphan-storage", response_model=OrphanStorageListResponse)
async def list_orphan_storage() -> OrphanStorageListResponse:
    """Every orphan-storage candidate, across every registered detector.

    ``provider_statuses`` names each detector that failed to run -- an
    outage must read as "could not check", never as "found nothing".
    """
    listing = await list_all_candidates()
    return OrphanStorageListResponse(
        candidates=[OrphanStorageCandidateResponse(**vars(c)) for c in listing.candidates],
        total_count=len(listing.candidates),
        total_size_bytes=sum(c.size_bytes for c in listing.candidates),
        provider_statuses=[OrphanStorageProviderStatusResponse(**vars(s)) for s in listing.statuses],
    )


@router.post(
    "/orphan-storage/deletion-requests",
    response_model=OrphanStorageDeletionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def propose_orphan_storage_deletion(
    body: OrphanStorageDeletionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrphanStorageDeletionRequestResponse:
    """Propose deleting one orphan-storage candidate -- a request, not a deletion.

    Creates a PENDING approval whose context names the registered action and
    the candidate. Nothing is deleted here and nothing can be: the only caller
    of ``delete_candidate`` is the post-approval executor, which runs after a
    human approves (#17038). Whether the candidate is still an orphan, and
    still past its grace period, is re-checked THEN rather than now, so a
    record that reappears between proposal and approval is refused instead of
    deleted.

    An unregistered provider is refused here rather than accepted and failed
    after approval -- a reviewer should never be asked to decide on a proposal
    that could not execute.
    """
    if body.provider not in registered_providers():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown orphan-storage provider",
        )

    approval = await ApprovalGateService(session).create_approval(
        title=f"Delete orphan storage: {body.provider}/{body.candidate_id}",
        approval_type=ApprovalType.DESTRUCTIVE_ACTION.value,
        description=body.reason or "Proposed from the orphan-storage admin view.",
        requested_by_agent=current_user.get("username"),
        context={
            "action": ORPHAN_STORAGE_DELETE,
            "provider": body.provider,
            "candidate_id": body.candidate_id,
        },
    )
    return OrphanStorageDeletionRequestResponse(
        approval_id=str(approval.id),
        status=approval.status,
        action=ORPHAN_STORAGE_DELETE,
        provider=body.provider,
        candidate_id=body.candidate_id,
    )
