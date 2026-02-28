# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Knowledge Base Source Verification Workflow API (Issue #1252).

Provides endpoints for reviewing and approving facts that were stored with
verification_status='pending_review' by the librarian assistant in collaborative
mode.

Endpoints:
- GET  /knowledge_base/verification/pending  - List pending-review facts
- POST /knowledge_base/verification/{fact_id}/approve - Approve a fact
- POST /knowledge_base/verification/{fact_id}/reject  - Reject a fact
- GET  /knowledge_base/verification/config             - Get verification config
- PUT  /knowledge_base/verification/config             - Update verification config

Related Issues: #1252 (Source Provenance Metadata & Verification Workflow)
"""

import logging
from datetime import datetime

from api.knowledge_models import (
    PendingSourceResponse,
    VerificationConfig,
    VerificationRequest,
)
from constants.threshold_constants import QueryDefaults
from fastapi import APIRouter, HTTPException, Path, Query, Request
from knowledge_factory import get_or_create_knowledge_base

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-verification"])

# Verification config stored in module state (lightweight, non-persistent).
# A future iteration may persist this to Redis (Issue #1252).
_verification_config: VerificationConfig = VerificationConfig()


def _raise_kb_unavailable() -> None:
    """Raise 500 when knowledge base is not initialised."""
    raise HTTPException(
        status_code=500,
        detail="Knowledge base not initialized - please check logs for errors",
    )


def _is_pending_review(metadata: dict) -> bool:
    """Return True when a fact's metadata marks it as pending review."""
    return metadata.get("verification_status") == "pending_review"


def _build_pending_response(fact: dict) -> PendingSourceResponse:
    """Convert a raw fact dict to a PendingSourceResponse (Issue #1252)."""
    meta = fact.get("metadata", {})
    return PendingSourceResponse(
        fact_id=fact["fact_id"],
        content=fact.get("content", ""),
        source_type=meta.get("source_type", "manual_upload"),
        quality_score=float(meta.get("quality_score", 0.0)),
        timestamp=fact.get("timestamp", meta.get("timestamp", "")),
        domain=meta.get("domain"),
        title=meta.get("title"),
        url=meta.get("source"),
    )


@router.get("/verification/pending")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_pending_verification",
    error_code_prefix="KNOWLEDGE",
)
async def list_pending_verification(
    limit: int = Query(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=200,
        description="Maximum number of pending facts to return",
    ),
    offset: int = Query(
        default=QueryDefaults.DEFAULT_OFFSET,
        ge=0,
        description="Pagination offset",
    ),
    req: Request = None,
):
    """List facts awaiting human verification.

    Issue #1252: Returns all knowledge facts with verification_status='pending_review'
    in paginated order.

    Returns:
    - status: success or error
    - pending: list of PendingSourceResponse objects
    - total: total matching count before pagination
    - limit / offset: echo of pagination params
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        _raise_kb_unavailable()

    all_facts = await kb.get_all_facts()
    pending_facts = [f for f in all_facts if _is_pending_review(f.get("metadata", {}))]

    total = len(pending_facts)
    page_facts = pending_facts[offset : offset + limit]

    pending_responses = [_build_pending_response(f) for f in page_facts]

    logger.info(
        "Verification queue: %d pending (returning %d, offset=%d)",
        total,
        len(pending_responses),
        offset,
    )
    return {
        "status": "success",
        "pending": [r.model_dump() for r in pending_responses],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.post("/verification/{fact_id}/approve")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_fact",
    error_code_prefix="KNOWLEDGE",
)
async def approve_fact(
    fact_id: str = Path(..., description="Fact UUID to approve"),
    body: VerificationRequest = None,
    req: Request = None,
):
    """Approve a pending fact, marking it as verified.

    Issue #1252: Sets verification_status='verified', records who approved it
    and when.

    Returns:
    - status: success or error
    - fact_id: the approved fact ID
    - verified_by / verified_at: approval metadata
    """
    if body is None:
        body = VerificationRequest()

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        _raise_kb_unavailable()

    now = datetime.now().isoformat()
    update_meta = {
        "verification_status": "verified",
        "verification_method": "user_approved",
        "verified_by": body.user,
        "verified_at": now,
    }

    result = await kb.update_fact(fact_id=fact_id, metadata=update_meta)
    if result.get("status") != "success":
        msg = result.get("message", "Update failed")
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    logger.info("Fact '%s' approved by '%s' at %s", fact_id, body.user, now)
    return {
        "status": "success",
        "fact_id": fact_id,
        "verified_by": body.user,
        "verified_at": now,
        "message": "Fact approved and marked as verified",
    }


@router.post("/verification/{fact_id}/reject")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reject_fact",
    error_code_prefix="KNOWLEDGE",
)
async def reject_fact(
    fact_id: str = Path(..., description="Fact UUID to reject"),
    body: VerificationRequest = None,
    req: Request = None,
):
    """Reject a pending fact and optionally delete it.

    Issue #1252: Sets verification_status='rejected'. When delete_on_reject=True,
    removes the fact entirely from the knowledge base.

    Returns:
    - status: success or error
    - fact_id: the rejected fact ID
    - deleted: True if the fact was also deleted
    """
    if body is None:
        body = VerificationRequest()

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        _raise_kb_unavailable()

    if body.delete_on_reject:
        del_result = await kb.delete_fact(fact_id)
        if del_result.get("status") == "success":
            logger.info("Fact '%s' rejected and deleted by '%s'", fact_id, body.user)
            return {
                "status": "success",
                "fact_id": fact_id,
                "deleted": True,
                "message": "Fact rejected and deleted from knowledge base",
            }
        msg = del_result.get("message", "Delete failed")
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    now = datetime.now().isoformat()
    update_meta = {
        "verification_status": "rejected",
        "verified_by": body.user,
        "verified_at": now,
    }
    result = await kb.update_fact(fact_id=fact_id, metadata=update_meta)
    if result.get("status") != "success":
        msg = result.get("message", "Update failed")
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=500, detail=msg)

    logger.info("Fact '%s' rejected (kept) by '%s'", fact_id, body.user)
    return {
        "status": "success",
        "fact_id": fact_id,
        "deleted": False,
        "message": "Fact marked as rejected",
    }


@router.get("/verification/config")
async def get_verification_config(req: Request = None):
    """Return current verification mode configuration.

    Issue #1252: Returns the active VerificationConfig used by the system.

    Returns:
    - status: success
    - config: VerificationConfig fields
    """
    return {
        "status": "success",
        "config": _verification_config.model_dump(),
    }


@router.put("/verification/config")
async def update_verification_config(
    body: VerificationConfig,
    req: Request = None,
):
    """Update verification mode configuration.

    Issue #1252: Allows switching between 'autonomous' and 'collaborative' modes
    at runtime. The librarian_assistant reads its own config on init; updating
    this endpoint affects the in-process module state used by the API layer and
    can be read by agent restarts.

    Returns:
    - status: success
    - config: Updated VerificationConfig fields
    """
    global _verification_config
    _verification_config = body
    logger.info(
        "Verification config updated: mode=%s, threshold=%.2f",
        body.mode,
        body.quality_threshold,
    )
    return {
        "status": "success",
        "config": _verification_config.model_dump(),
        "message": "Verification configuration updated",
    }
