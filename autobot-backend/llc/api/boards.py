# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC boards API routes (GH#8221).

Routes:
  POST  /api/llc/boards/kanban         — get or create kanban board for a project
  POST  /api/llc/boards/sprint         — get or create sprint board for a sprint
  GET   /api/llc/boards/{board_id}     — get board metadata + columns
  GET   /api/llc/boards/{board_id}/items — get board with work items grouped by column
  POST  /api/llc/boards/{board_id}/move  — move work item to a column
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.deps import get_session, service_dep
from user_management.services import TenantContext

from ..exceptions import WipLimitExceeded
from ..services.board import BoardService
from ..services.work_item_service import InvalidTransition

logger = get_logger(__name__)
router = APIRouter(prefix="/boards", tags=["llc-boards"])
_service = service_dep(BoardService)


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------


class KanbanBoardRequest(BaseModel):
    company_id: str
    project_id: str
    name: Optional[str] = None


class SprintBoardRequest(BaseModel):
    company_id: str
    sprint_id: str
    name: Optional[str] = None


class MoveItemRequest(BaseModel):
    work_item_id: str
    column_id: str
    actor_id: Optional[str] = None


# ------------------------------------------------------------------
# Response helpers
# ------------------------------------------------------------------


def _board_response(board: Any) -> Dict[str, Any]:
    return {
        "id": str(board.id),
        "company_id": str(board.company_id),
        "project_id": str(board.project_id) if board.project_id else None,
        "sprint_id": str(board.sprint_id) if board.sprint_id else None,
        "type": board.type.value if hasattr(board.type, "value") else board.type,
        "name": board.name,
        "created_at": board.created_at.isoformat() if board.created_at else None,
        "updated_at": board.updated_at.isoformat() if board.updated_at else None,
        "columns": [
            {
                "id": str(col.id),
                "name": col.name,
                "position": col.position,
                "status_filter": col.status_filter,
                "wip_limit": col.wip_limit,
            }
            for col in board.columns
        ],
    }


def _work_item_summary(item: Any) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "identifier": item.identifier,
        "title": item.title,
        "type": item.type.value if hasattr(item.type, "value") else item.type,
        "status": item.status.value if hasattr(item.status, "value") else item.status,
        "priority": item.priority.value if hasattr(item.priority, "value") else item.priority,
        "story_points": item.story_points,
        "assignee_agent_id": str(item.assignee_agent_id) if item.assignee_agent_id else None,
        "assignee_user_id": str(item.assignee_user_id) if item.assignee_user_id else None,
    }


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


def _board_summary(board: Any) -> Dict[str, Any]:
    """Board metadata without columns — safe to build outside an eager load (GH#10219)."""
    return {
        "id": str(board.id),
        "company_id": str(board.company_id),
        "project_id": str(board.project_id) if board.project_id else None,
        "sprint_id": str(board.sprint_id) if board.sprint_id else None,
        "type": board.type.value if hasattr(board.type, "value") else board.type,
        "name": board.name,
        "created_at": board.created_at.isoformat() if board.created_at else None,
        "updated_at": board.updated_at.isoformat() if board.updated_at else None,
    }


@router.get("")
async def list_company_boards(
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """List all boards for the caller's company (GH#10219 — un-orphans the Sprint
    and Kanban board views, which previously had no UI entry point).

    Tenant-scoped via ``ctx.org_id`` so there is no cross-tenant exposure (the
    IDOR class fixed for sprints.py in #10148 is avoided here by construction).
    """
    boards = await svc.list_boards(session, str(ctx.org_id))
    return [_board_summary(b) for b in boards]


@router.post("/kanban", status_code=201)
async def create_kanban_board(
    body: KanbanBoardRequest,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
) -> Dict[str, Any]:
    """Get or create the kanban board for a project."""
    try:
        board = await svc.get_or_create_kanban(session, body.company_id, body.project_id, name=body.name)
        await session.commit()
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Internal server error")
    return _board_response(board)


@router.post("/sprint", status_code=201)
async def create_sprint_board(
    body: SprintBoardRequest,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
) -> Dict[str, Any]:
    """Get or create the sprint board for a sprint."""
    try:
        board = await svc.get_or_create_sprint_board(session, body.company_id, body.sprint_id, name=body.name)
        await session.commit()
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Internal server error")
    return _board_response(board)


@router.get("/{board_id}")
async def get_board(
    board_id: str,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
) -> Dict[str, Any]:
    """Get board metadata and column configuration."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")
    board = await svc.get_board(session, board_id)
    if board is None:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
    return _board_response(board)


@router.get("/{board_id}/items")
async def get_board_items(
    board_id: str,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
) -> Dict[str, Any]:
    """Return all work items grouped by board column."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")
    try:
        result = await svc.get_board_items(session, board_id)
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error")

    board = result["board"]
    columns_with_items: List[Dict[str, Any]] = []
    for col_data in result["columns"]:
        columns_with_items.append(
            {
                "id": col_data["id"],
                "name": col_data["name"],
                "position": col_data["position"],
                "status_filter": col_data["status_filter"],
                "wip_limit": col_data["wip_limit"],
                "items": [_work_item_summary(i) for i in col_data["items"]],
                "item_count": len(col_data["items"]),
            }
        )

    return {
        "board": _board_response(board),
        "columns": columns_with_items,
    }


@router.post("/{board_id}/move")
async def move_item(
    board_id: str,
    body: MoveItemRequest,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
) -> Dict[str, Any]:
    """Move a work item to a board column, enforcing WIP limits."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")

    try:
        updated_item = await svc.move_item(
            session,
            board_id=board_id,
            work_item_id=body.work_item_id,
            column_id=body.column_id,
            actor_id=body.actor_id,
        )
        await session.commit()
    except WipLimitExceeded as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "WIP_LIMIT_EXCEEDED",
                "column": exc.column_name,
                "wip_limit": exc.wip_limit,
                "current_count": exc.current_count,
            },
        )
    except InvalidTransition as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=422, detail="Internal server error")
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error")

    return _work_item_summary(updated_item)
