# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC heartbeat context API (GH#8236).

Routes:
  GET  /api/llc/agent/context/{item_id}  — get assembled heartbeat context
"""

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..kb.context_builder import HeartbeatContextBuilder
from ..kb.rag_assembler import LLCRAGAssembler
from ..services.goal import GoalService
from ..services.work_item_service import WorkItemService

router = APIRouter(prefix="/agent", tags=["llc-context"])


def _get_context_services() -> Dict[str, Any]:
    """Factory for context builder dependencies."""
    return {
        "rag_assembler": LLCRAGAssembler(),
        "goal_service": GoalService(),
        "work_item_service": WorkItemService(),
    }


@router.get("/context/{item_id}")
async def get_context(
    item_id: str,
    mode: str = "fat",
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Get assembled heartbeat context for a work item (GH#8236).

    Returns rich context with company goals, project/agent KB, and similar
    past work items. Context is compressed with gzip before storage.

    Args:
        item_id: Work item UUID
        mode: "thin" or "fat" context mode
        session: DB session
        ctx: Tenant context

    Returns:
        Dict with assembled context:
        - work_item_id, work_item_detail
        - goal_ancestry (parent chain)
        - company_context, project_context, agent_memory (RAG results)
        - similar_past_work (completed items)
        - api_base, agent_api_key (runtime injection)

    Raises:
        404: Work item not found
        422: Invalid context_mode
    """
    try:
        work_item_id = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    services = _get_context_services()
    builder = HeartbeatContextBuilder(
        rag_assembler=services["rag_assembler"],
        goal_service=services["goal_service"],
        work_item_service=services["work_item_service"],
    )

    # Build context in requested mode
    try:
        context_dict = await builder.build(
            session=session,
            agent_id=_current_user.get("id", "unknown"),
            work_item_id=work_item_id,
            context_mode=mode,
        )
    except ValueError as e:
        error_msg = str(e)
        if "Unknown context_mode" in error_msg:
            raise HTTPException(status_code=422, detail=error_msg)
        raise HTTPException(status_code=404, detail=error_msg)

    return context_dict
