# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC BoardService — Kanban and Sprint board management (GH#8221).

Responsibilities:
  - get_or_create_kanban  : idempotent kanban board per (company, project).
  - get_or_create_sprint_board: idempotent sprint board per (company, sprint).
  - get_board_items       : work items grouped by board column.
  - move_item             : column move → status transition + WIP-limit guard
                            + Redis publish on llc:board:{board_id}.

Real-time channel: ``llc:board:{board_id}`` — published after every successful
move.  Frontend (Phase 6) subscribes via the existing WebSocket event bus.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client

from ..exceptions import WipLimitExceeded
from ..models.board import LLCBoard, LLCBoardColumn
from ..models.enums import BoardType, WorkItemStatus
from ..models.work_item import LLCWorkItem
from .base import LLCServiceBase
from .work_item_service import WorkItemService

logger = logging.getLogger(__name__)

# Default column definitions shared by both board types.
_DEFAULT_COLUMNS: List[Dict[str, Any]] = [
    {"name": "Backlog", "position": 0, "status_filter": [WorkItemStatus.BACKLOG.value], "wip_limit": None},
    {"name": "Ready", "position": 1, "status_filter": [WorkItemStatus.READY.value], "wip_limit": None},
    {"name": "In Progress", "position": 2, "status_filter": [WorkItemStatus.IN_PROGRESS.value], "wip_limit": None},
    {"name": "In Review", "position": 3, "status_filter": [WorkItemStatus.IN_REVIEW.value], "wip_limit": None},
    {"name": "Done", "position": 4, "status_filter": [WorkItemStatus.DONE.value], "wip_limit": None},
]


class BoardService(LLCServiceBase):
    """Service for LLC board management."""

    # ------------------------------------------------------------------
    # Board creation helpers
    # ------------------------------------------------------------------

    async def get_or_create_kanban(
        self,
        session: AsyncSession,
        company_id: str,
        project_id: str,
        name: Optional[str] = None,
    ) -> LLCBoard:
        """Return the kanban board for *project_id*, creating it if absent."""
        result = await session.execute(
            select(LLCBoard).where(
                LLCBoard.company_id == uuid.UUID(company_id),
                LLCBoard.project_id == uuid.UUID(project_id),
                LLCBoard.type == BoardType.KANBAN,
            )
        )
        board = result.scalar_one_or_none()
        if board is None:
            board = await self._create_board(
                session,
                company_id=company_id,
                board_type=BoardType.KANBAN,
                name=name or "Kanban Board",
                project_id=project_id,
            )
        return board

    async def get_or_create_sprint_board(
        self,
        session: AsyncSession,
        company_id: str,
        sprint_id: str,
        name: Optional[str] = None,
    ) -> LLCBoard:
        """Return the sprint board for *sprint_id*, creating it if absent."""
        result = await session.execute(
            select(LLCBoard).where(
                LLCBoard.company_id == uuid.UUID(company_id),
                LLCBoard.sprint_id == uuid.UUID(sprint_id),
                LLCBoard.type == BoardType.SPRINT,
            )
        )
        board = result.scalar_one_or_none()
        if board is None:
            board = await self._create_board(
                session,
                company_id=company_id,
                board_type=BoardType.SPRINT,
                name=name or "Sprint Board",
                sprint_id=sprint_id,
            )
        return board

    async def _create_board(
        self,
        session: AsyncSession,
        company_id: str,
        board_type: BoardType,
        name: str,
        project_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
    ) -> LLCBoard:
        board = LLCBoard(
            company_id=uuid.UUID(company_id),
            project_id=uuid.UUID(project_id) if project_id else None,
            sprint_id=uuid.UUID(sprint_id) if sprint_id else None,
            type=board_type,
            name=name,
        )
        session.add(board)
        await session.flush()  # populate board.id before FK insert

        for col_def in _DEFAULT_COLUMNS:
            session.add(
                LLCBoardColumn(
                    board_id=board.id,
                    name=col_def["name"],
                    position=col_def["position"],
                    status_filter=col_def["status_filter"],
                    wip_limit=col_def["wip_limit"],
                )
            )
        await session.flush()
        await session.refresh(board)
        return board

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_board(self, session: AsyncSession, board_id: str) -> Optional[LLCBoard]:
        result = await session.execute(select(LLCBoard).where(LLCBoard.id == uuid.UUID(board_id)))
        return result.scalar_one_or_none()

    async def list_boards(self, session: AsyncSession, company_id: str) -> Sequence[LLCBoard]:
        """All boards for a company, newest first (GH#10219 — board reachability)."""
        result = await session.execute(
            select(LLCBoard).where(LLCBoard.company_id == uuid.UUID(company_id)).order_by(LLCBoard.created_at.desc())
        )
        return result.scalars().all()

    async def get_board_items(self, session: AsyncSession, board_id: str) -> Dict[str, Any]:
        """Return board columns with work items grouped per column.

        Result shape::

            {
                "board": {id, name, type, ...},
                "columns": [
                    {
                        "id": "...",
                        "name": "In Progress",
                        "position": 2,
                        "status_filter": ["in_progress"],
                        "wip_limit": null,
                        "items": [ <LLCWorkItem>, ... ],
                    },
                    ...
                ],
            }
        """
        board = await self.get_board(session, board_id)
        if board is None:
            raise ValueError(f"Board {board_id} not found")

        # Collect all statuses covered by this board's columns so we can
        # fetch matching work items in one query.
        all_statuses: List[str] = []
        for col in board.columns:
            all_statuses.extend(col.status_filter)

        # Build scope filter (project or sprint).
        scope_filter = []
        if board.project_id is not None:
            scope_filter.append(LLCWorkItem.project_id == board.project_id)
        if board.sprint_id is not None:
            scope_filter.append(LLCWorkItem.sprint_id == board.sprint_id)

        items_result = await session.execute(
            select(LLCWorkItem).where(
                LLCWorkItem.company_id == board.company_id,
                LLCWorkItem.status.in_(all_statuses),
                *scope_filter,
            )
        )
        items: Sequence[LLCWorkItem] = items_result.scalars().all()

        # Group items by column (each item lands in the first column whose
        # status_filter contains the item's current status).
        status_to_column: Dict[str, str] = {}
        for col in board.columns:
            for s in col.status_filter:
                status_to_column[s] = str(col.id)

        column_items: Dict[str, List[LLCWorkItem]] = {str(col.id): [] for col in board.columns}
        for item in items:
            col_id = status_to_column.get(str(item.status) if isinstance(item.status, str) else item.status.value)
            if col_id and col_id in column_items:
                column_items[col_id].append(item)

        return {
            "board": board,
            "columns": [
                {
                    "id": str(col.id),
                    "name": col.name,
                    "position": col.position,
                    "status_filter": col.status_filter,
                    "wip_limit": col.wip_limit,
                    "items": column_items[str(col.id)],
                }
                for col in board.columns
            ],
        }

    # ------------------------------------------------------------------
    # Move
    # ------------------------------------------------------------------

    async def move_item(
        self,
        session: AsyncSession,
        board_id: str,
        work_item_id: str,
        column_id: str,
        actor_id: Optional[str] = None,
    ) -> LLCWorkItem:
        """Move *work_item_id* into *column_id*, enforcing WIP limit.

        Steps:
        1. Load the board and target column.
        2. Count current items in the target column; raise WipLimitExceeded
           if at limit.
        3. Derive the new work item status from column.status_filter[0].
        4. Delegate the status transition to WorkItemService.
        5. Publish ``llc:board:{board_id}`` to Redis.
        """
        board = await self.get_board(session, board_id)
        if board is None:
            raise ValueError(f"Board {board_id} not found")

        col_result = await session.execute(
            select(LLCBoardColumn).where(
                LLCBoardColumn.id == uuid.UUID(column_id),
                LLCBoardColumn.board_id == uuid.UUID(board_id),
            )
        )
        column = col_result.scalar_one_or_none()
        if column is None:
            raise ValueError(f"Column {column_id} not found on board {board_id}")

        # WIP limit check
        if column.wip_limit is not None:
            scope_filter = []
            if board.project_id is not None:
                scope_filter.append(LLCWorkItem.project_id == board.project_id)
            if board.sprint_id is not None:
                scope_filter.append(LLCWorkItem.sprint_id == board.sprint_id)

            count_result = await session.execute(
                select(func.count(LLCWorkItem.id)).where(
                    LLCWorkItem.company_id == board.company_id,
                    LLCWorkItem.status.in_(column.status_filter),
                    *scope_filter,
                )
            )
            current_count = count_result.scalar_one()
            if current_count >= column.wip_limit:
                raise WipLimitExceeded(column.name, column.wip_limit, current_count)

        if not column.status_filter:
            raise ValueError(f"Column {column_id} has no status_filter configured")

        new_status = WorkItemStatus(column.status_filter[0])
        work_item_svc = WorkItemService(activity_log=self.activity_log)
        updated_item = await work_item_svc.transition_status(session, work_item_id, new_status)

        await self._publish_board_event(
            board_id=board_id,
            event_type="llc:board_updated",
            work_item_id=work_item_id,
            column_id=column_id,
            new_status=new_status.value,
            actor_id=actor_id,
        )
        return updated_item

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _publish_board_event(
        self,
        board_id: str,
        event_type: str,
        work_item_id: str,
        column_id: str,
        new_status: str,
        actor_id: Optional[str],
    ) -> None:
        """Publish a board update event to Redis pub/sub.

        Channel: ``llc:board:{board_id}``
        Never raises — publishing failures are logged but must not break
        the calling move_item operation.
        """
        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable — skipping llc:board:%s publish", board_id)
            return
        try:
            payload = json.dumps(
                {
                    "event_type": event_type,
                    "board_id": board_id,
                    "work_item_id": work_item_id,
                    "column_id": column_id,
                    "new_status": new_status,
                    "actor_id": actor_id,
                }
            )
            await redis.publish(f"llc:board:{board_id}", payload)
        except Exception:
            logger.exception("Failed to publish llc:board:%s event", board_id)
