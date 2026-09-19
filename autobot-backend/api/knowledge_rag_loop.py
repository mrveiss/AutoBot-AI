# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base RAG Autonomous Improvement Loop API - Extracted from
knowledge_rag.py (#16665) to keep that file's own growth within its
grandfathered line-count ceiling (#14236). Loop status/approve/reject never
return knowledge-base facts, so this carries no fact-visibility concern.

Endpoints:
- GET  /loop/status  - Autonomous improvement loop status
- POST /loop/approve - Promote the pending staging variant to production
- POST /loop/reject  - Discard the pending staging variant
"""

from fastapi import APIRouter, Depends, HTTPException

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.schemas.rag import (
    LoopApproveResponse,
    LoopRejectResponse,
    LoopStatusResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-rag-loop"])


@router.get("/loop/status", response_model=LoopStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_loop_status",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def get_loop_status(
    current_user: dict = Depends(get_current_user),
):
    """Get autonomous improvement loop status.

    Returns last run time, variants tested, winner, current baseline config,
    and any variant pending human approval.

    Issue #4680.
    """
    from services.rag_config import get_rag_config

    cfg = get_rag_config()

    # Import lazily to avoid hard startup dependency
    try:
        from services.knowledge.autonomous_loop import get_loop_runner as get_loop_orchestrator

        orchestrator = await get_loop_orchestrator(None, dry_run=cfg.autonomous_loop_dry_run)
        status = orchestrator.get_status()
    except Exception as exc:
        logger.warning("Loop status unavailable: %s", exc)
        from services.knowledge.autonomous_loop import LoopStatus

        status = LoopStatus(
            enabled=cfg.autonomous_loop_enabled,
            dry_run=cfg.autonomous_loop_dry_run,
            last_run=None,
        )

    return {
        "loop_status": status.to_dict(),
        "current_config": cfg.to_dict(),
    }


@router.post("/loop/approve", response_model=LoopApproveResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="approve_loop_variant",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def approve_loop_variant(
    current_user: dict = Depends(get_current_user),
):
    """Promote the pending staging variant to production RAGConfig.

    The autonomous loop stores a "pending approval" variant when the improvement
    margin is below the auto-promotion threshold.  This endpoint applies it.

    Returns 409 if no variant is pending.

    Issue #4680.
    """
    from services.knowledge.autonomous_loop import get_loop_runner as get_loop_orchestrator
    from services.rag_config import get_rag_config

    cfg = get_rag_config()
    orchestrator = await get_loop_orchestrator(None, dry_run=cfg.autonomous_loop_dry_run)
    applied = await orchestrator.approve_pending()

    if not applied:
        raise HTTPException(status_code=409, detail="No variant pending approval")

    return {
        "message": "Pending variant promoted to production config",
        "config": get_rag_config().to_dict(),
    }


@router.post("/loop/reject", response_model=LoopRejectResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reject_loop_variant",
    error_code_prefix="KNOWLEDGE_RAG",
)
async def reject_loop_variant(
    current_user: dict = Depends(get_current_user),
):
    """Discard the pending staging variant without applying it to production RAGConfig.

    The autonomous loop stores a "pending approval" variant when the improvement
    margin is below the auto-promotion threshold.  This endpoint clears it.

    Returns 409 if no variant is pending.

    Issue #4916.
    """
    from services.knowledge.autonomous_loop import get_loop_runner as get_loop_orchestrator
    from services.rag_config import get_rag_config

    cfg = get_rag_config()
    orchestrator = await get_loop_orchestrator(None, dry_run=cfg.autonomous_loop_dry_run)
    cleared = await orchestrator.reject_pending()

    if not cleared:
        raise HTTPException(status_code=409, detail="No variant pending approval")

    return {"message": "Pending variant rejected and cleared"}
