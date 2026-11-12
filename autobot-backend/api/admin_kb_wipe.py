# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin API: preview and PROPOSE a knowledge-base wipe (#21048, #17038).

Endpoints:
    GET  /api/admin/knowledge-wipe           read only -- what a wipe would delete, with counts (dry run)
    POST /api/admin/knowledge-wipe/requests  PROPOSE the wipe -- creates (or reuses) a PENDING approval

Neither route deletes anything. Nothing runs until an admin approves it in the Approvals inbox, and it is
never auto-approved. The executor lives in ``services.kb_wipe_action``. ``POST /knowledge_base/clear_all`` and
the MCP vector ``flush`` operation propose through the same ``services.kb_wipe_request.request_kb_wipe``.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from services.kb_wipe_action import plan_kb_wipe, register_kb_wipe_action
from services.kb_wipe_request import request_kb_wipe

router = APIRouter(prefix="/admin", dependencies=[Depends(check_admin_permission)])

# Registered at this router's import time so the executor exists before any approve().
register_kb_wipe_action()


@router.get("/knowledge-wipe")
async def knowledge_wipe_plan() -> dict:
    """Read only: the databases and indexes a wipe would delete."""
    return await plan_kb_wipe()


@router.post("/knowledge-wipe/requests", status_code=status.HTTP_201_CREATED)
async def propose_knowledge_wipe(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Propose the wipe -- a request, not an execution."""
    return await request_kb_wipe(current_user, session)
