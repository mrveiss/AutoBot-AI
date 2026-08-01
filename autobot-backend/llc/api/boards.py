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
  PUT   /api/llc/boards/{board_id}     — rename a board
  DELETE /api/llc/boards/{board_id}    — delete a board and its columns
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


class BoardUpdateRequest(BaseModel):
    """GH#12695: rename a board. Only the name is updatable — see BoardService.update_board."""

    name: str


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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Get or create the kanban board for a project."""
    # GH#10296: never trust the body company_id — bind to the caller's org.
    if str(body.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Company not found")
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Get or create the sprint board for a sprint."""
    # GH#10296: never trust the body company_id — bind to the caller's org.
    if str(body.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Company not found")
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Get board metadata and column configuration."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")
    board = await svc.get_board(session, board_id)
    # GH#10296: 404 (not 403) on cross-tenant to avoid existence disclosure.
    if board is None or str(board.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
    return _board_response(board)


@router.get("/{board_id}/items")
async def get_board_items(
    board_id: str,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Return all work items grouped by board column."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")
    # GH#10296: verify tenant ownership before exposing any board items.
    owner = await svc.get_board(session, board_id)
    if owner is None or str(owner.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
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


@router.put("/{board_id}")
async def update_board(
    board_id: str,
    body: BoardUpdateRequest,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Rename a board (GH#12695). Boards were the only entity with no backend update."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")

    # GH#10296: verify tenant ownership BEFORE any cross-tenant mutation.
    owner = await svc.get_board(session, board_id)
    if owner is None or str(owner.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

    board = await svc.update_board(session, board_id, body.name)
    if board is None:
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")
    await session.commit()
    return _board_response(board)


@router.delete("/{board_id}", status_code=204)
async def delete_board(
    board_id: str,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Delete a board and its columns (GH#12695).

    Work items are untouched — they belong to the project, not the board, so
    deleting a view must not destroy the work it displays.
    """
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")

    owner = await svc.get_board(session, board_id)
    if owner is None or str(owner.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

    await svc.delete_board(session, board_id)
    await session.commit()


@router.post("/{board_id}/move")
async def move_item(
    board_id: str,
    body: MoveItemRequest,
    session: AsyncSession = Depends(get_session),
    svc: BoardService = Depends(_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Move a work item to a board column, enforcing WIP limits."""
    try:
        uuid.UUID(board_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid board_id")

    # GH#10296: verify tenant ownership BEFORE any cross-tenant mutation.
    owner = await svc.get_board(session, board_id)
    if owner is None or str(owner.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail=f"Board {board_id} not found")

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
        # #12740: the service already computed the exact, useful reason
        # ("Cannot transition from X to Y. Allowed: [...]"). Replacing it with a
        # generic 422 "Internal server error" threw that away, so the UI could
        # not tell the user what went wrong or what IS allowed. The message is
        # purely domain-level — statuses and permitted transitions, no internals
        # — so it is safe to surface. 409 Conflict is the correct code: the
        # request is well-formed (422 implies malformed), it conflicts with the
        # item's current state.
        logger.info("Rejected illegal work-item transition: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error")

    return _work_item_summary(updated_item)
