# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Zero-count Chroma collections: report them, and PROPOSE their removal (#19725).

Endpoints (mounted under ``/knowledge/chroma``, admin only):
    GET  /knowledge/chroma/empty-collections                   read-only report
    POST /knowledge/chroma/empty-collections/cleanup-requests  PROPOSE deleting one

The POST creates a PENDING approval and deletes nothing; the deletion runs only from the post-approval
handler after a human approves (#17038).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas_knowledge_chroma import (
    EmptyCollectionCleanupRequest,
    EmptyCollectionCleanupResponse,
    EmptyCollectionsResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from services.approval_gate_service import ApprovalGateService
from services.chroma_empty_collections import ACTION as EMPTY_COLLECTION_DELETE
from services.chroma_empty_collections import register_cleanup_action, scan_empty_collections
from services.kb_cleanup_proposals import cleanup_proposal

router = APIRouter(prefix="/empty-collections", dependencies=[Depends(check_admin_permission)])

# Registered at this router's import time so the handler exists before any approve() can reach it.
register_cleanup_action()


@router.get("", response_model=EmptyCollectionsResponse)
async def list_empty_collections() -> EmptyCollectionsResponse:
    """Collections holding zero vectors, plus those that could not be counted (read-only)."""
    report = await scan_empty_collections()
    return EmptyCollectionsResponse(total=report.total, empty=report.empty, unreadable=report.unreadable)


@router.post("/cleanup-requests", response_model=EmptyCollectionCleanupResponse, status_code=status.HTTP_201_CREATED)
async def propose_empty_collection_cleanup(
    body: EmptyCollectionCleanupRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmptyCollectionCleanupResponse:
    """Propose deleting one zero-count collection -- a request, not a deletion.

    A collection that is not currently reported empty is refused, so a reviewer is never asked to decide
    on something that could not execute. The handler re-checks the count when the proposal is approved.
    """
    if body.collection not in (await scan_empty_collections()).empty:
        raise HTTPException(status.HTTP_409_CONFLICT, "That collection is not an empty collection")
    approval = await ApprovalGateService(session).create_approval(
        **cleanup_proposal(
            current_user,
            title=f"Delete empty vector collection: {body.collection}",
            description="The collection holds zero vectors. Approving deletes the collection; it is re-checked first.",
            context={"action": EMPTY_COLLECTION_DELETE, "collection": body.collection},
        )
    )
    return EmptyCollectionCleanupResponse(
        approval_id=str(approval.id),
        status=approval.status,
        action=EMPTY_COLLECTION_DELETE,
        collection=body.collection,
    )
