# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for LLC BoardService (GH#8221)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.exceptions import WipLimitExceeded
from llc.models.enums import BoardType, WorkItemPriority, WorkItemStatus, WorkItemType
from llc.services.board import _DEFAULT_COLUMNS, BoardService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_board(
    board_type: BoardType = BoardType.KANBAN,
    project_id: uuid.UUID | None = None,
    sprint_id: uuid.UUID | None = None,
    columns: list | None = None,
) -> MagicMock:
    board = MagicMock()
    board.id = uuid.uuid4()
    board.company_id = uuid.uuid4()
    board.project_id = project_id
    board.sprint_id = sprint_id
    board.type = board_type
    board.name = "Test Board"
    board.columns = columns or []
    return board


def _make_column(
    board_id: uuid.UUID,
    name: str = "In Progress",
    position: int = 2,
    status_filter: list | None = None,
    wip_limit: int | None = None,
) -> MagicMock:
    col = MagicMock()
    col.id = uuid.uuid4()
    col.board_id = board_id
    col.name = name
    col.position = position
    col.status_filter = status_filter or [WorkItemStatus.IN_PROGRESS.value]
    col.wip_limit = wip_limit
    return col


def _make_work_item(status: WorkItemStatus = WorkItemStatus.READY) -> MagicMock:
    item = MagicMock()
    item.id = uuid.uuid4()
    item.company_id = uuid.uuid4()
    item.identifier = "WI-001"
    item.title = "Test task"
    item.type = WorkItemType.TASK
    item.status = status
    item.priority = WorkItemPriority.MEDIUM
    item.story_points = None
    item.assignee_agent_id = None
    item.assignee_user_id = None
    return item


def _make_session(scalar_value=None, scalars_all=None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    if scalars_all is not None:
        result.scalars.return_value.all.return_value = scalars_all
    else:
        result.scalars.return_value.all.return_value = []
    session.execute.return_value = result
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def service():
    return BoardService()


# ---------------------------------------------------------------------------
# get_or_create_kanban
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_kanban_returns_existing(service):
    company_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    existing_board = _make_board(board_type=BoardType.KANBAN)
    session = _make_session(scalar_value=existing_board)

    board = await service.get_or_create_kanban(session, company_id, project_id)

    assert board is existing_board
    # No flush should happen — board was not created
    session.flush.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_kanban_creates_when_absent(service):
    company_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    session = _make_session(scalar_value=None)

    with patch("llc.services.board.LLCBoard") as MockBoard, patch("llc.services.board.LLCBoardColumn") as MockColumn:
        MockBoard.return_value = MagicMock()
        MockBoard.return_value.id = uuid.uuid4()
        MockBoard.return_value.columns = []

        # Simulate refresh populating board.columns
        async def _refresh(obj):
            obj.columns = []

        session.refresh.side_effect = _refresh

        board = await service.get_or_create_kanban(session, company_id, project_id)

        # Flush called twice: once for board PK, once for columns
        assert session.flush.call_count == 2
        # One LLCBoardColumn added per default column definition
        assert MockColumn.call_count == len(_DEFAULT_COLUMNS)


# ---------------------------------------------------------------------------
# get_or_create_sprint_board
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_sprint_board_returns_existing(service):
    company_id = str(uuid.uuid4())
    sprint_id = str(uuid.uuid4())
    existing_board = _make_board(board_type=BoardType.SPRINT)
    session = _make_session(scalar_value=existing_board)

    board = await service.get_or_create_sprint_board(session, company_id, sprint_id)

    assert board is existing_board
    session.flush.assert_not_called()


# ---------------------------------------------------------------------------
# get_board_items
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_board_items_raises_on_missing_board(service):
    session = _make_session(scalar_value=None)
    with pytest.raises(ValueError, match="not found"):
        await service.get_board_items(session, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_get_board_items_groups_items_by_column(service):
    board_id = uuid.uuid4()
    col_ready = _make_column(board_id, name="Ready", position=1, status_filter=["ready"])
    col_in_progress = _make_column(board_id, name="In Progress", position=2, status_filter=["in_progress"])
    board = _make_board(columns=[col_ready, col_in_progress])

    item_ready = _make_work_item(status=WorkItemStatus.READY)
    item_wip = _make_work_item(status=WorkItemStatus.IN_PROGRESS)

    session = AsyncMock()

    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        result = MagicMock()
        if call_count == 0:
            result.scalar_one_or_none.return_value = board
        else:
            result.scalars.return_value.all.return_value = [item_ready, item_wip]
        call_count += 1
        return result

    session.execute.side_effect = fake_execute

    result = await service.get_board_items(session, str(board_id))

    assert result["board"] is board
    cols = {c["name"]: c for c in result["columns"]}
    assert cols["Ready"]["items"] == [item_ready]
    assert cols["In Progress"]["items"] == [item_wip]


# ---------------------------------------------------------------------------
# move_item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_item_enforces_wip_limit(service):
    board_id = uuid.uuid4()
    col = _make_column(board_id, wip_limit=2)
    board = _make_board(columns=[col])

    # Build a session that returns: board on first call, column on second,
    # then 2 existing items on third (at limit).
    existing_items = [_make_work_item(WorkItemStatus.IN_PROGRESS), _make_work_item(WorkItemStatus.IN_PROGRESS)]

    call_count = 0

    session = AsyncMock()

    async def fake_execute(stmt):
        nonlocal call_count
        result = MagicMock()
        if call_count == 0:
            result.scalar_one_or_none.return_value = board
        elif call_count == 1:
            result.scalar_one_or_none.return_value = col
        else:
            result.scalars.return_value.all.return_value = existing_items
        call_count += 1
        return result

    session.execute.side_effect = fake_execute

    with pytest.raises(WipLimitExceeded) as exc_info:
        await service.move_item(
            session,
            board_id=str(board_id),
            work_item_id=str(uuid.uuid4()),
            column_id=str(col.id),
        )

    assert exc_info.value.wip_limit == 2
    assert exc_info.value.current_count == 2


@pytest.mark.asyncio
async def test_move_item_raises_on_missing_board(service):
    session = _make_session(scalar_value=None)
    with pytest.raises(ValueError, match="not found"):
        await service.move_item(
            session,
            board_id=str(uuid.uuid4()),
            work_item_id=str(uuid.uuid4()),
            column_id=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_move_item_raises_on_missing_column(service):
    board = _make_board()
    session = AsyncMock()
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        result = MagicMock()
        if call_count == 0:
            result.scalar_one_or_none.return_value = board
        else:
            result.scalar_one_or_none.return_value = None
        call_count += 1
        return result

    session.execute.side_effect = fake_execute

    with pytest.raises(ValueError, match="not found on board"):
        await service.move_item(
            session,
            board_id=str(board.id),
            work_item_id=str(uuid.uuid4()),
            column_id=str(uuid.uuid4()),
        )


@pytest.mark.asyncio
async def test_move_item_transitions_status_and_publishes(service):
    board_id = uuid.uuid4()
    col = _make_column(board_id, status_filter=["in_progress"], wip_limit=None)
    board = _make_board(columns=[col])
    updated_item = _make_work_item(WorkItemStatus.IN_PROGRESS)

    session = AsyncMock()
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        result = MagicMock()
        if call_count == 0:
            result.scalar_one_or_none.return_value = board
        elif call_count == 1:
            result.scalar_one_or_none.return_value = col
        call_count += 1
        return result

    session.execute.side_effect = fake_execute

    with (
        patch("llc.services.board.WorkItemService") as MockWIS,
        patch("llc.services.board.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn,
    ):

        mock_wis_instance = AsyncMock()
        mock_wis_instance.transition_status = AsyncMock(return_value=updated_item)
        MockWIS.return_value = mock_wis_instance

        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_redis_fn.return_value = mock_redis

        result = await service.move_item(
            session,
            board_id=str(board_id),
            work_item_id=str(updated_item.id),
            column_id=str(col.id),
        )

    assert result is updated_item
    mock_wis_instance.transition_status.assert_called_once_with(
        session, str(updated_item.id), WorkItemStatus.IN_PROGRESS
    )
    mock_redis.publish.assert_called_once()
    channel, payload = mock_redis.publish.call_args[0]
    assert channel == f"llc:board:{board_id}"
    data = json.loads(payload)
    assert data["event_type"] == "llc:board_updated"
    assert data["board_id"] == str(board_id)
    assert data["new_status"] == "in_progress"


@pytest.mark.asyncio
async def test_move_item_publishes_silently_when_redis_unavailable(service):
    board_id = uuid.uuid4()
    col = _make_column(board_id, status_filter=["in_review"], wip_limit=None)
    board = _make_board(columns=[col])
    updated_item = _make_work_item(WorkItemStatus.IN_REVIEW)

    session = AsyncMock()
    call_count = 0

    async def fake_execute(stmt):
        nonlocal call_count
        result = MagicMock()
        if call_count == 0:
            result.scalar_one_or_none.return_value = board
        elif call_count == 1:
            result.scalar_one_or_none.return_value = col
        call_count += 1
        return result

    session.execute.side_effect = fake_execute

    with (
        patch("llc.services.board.WorkItemService") as MockWIS,
        patch("llc.services.board.get_async_redis_client", new_callable=AsyncMock) as mock_redis_fn,
    ):

        mock_wis_instance = AsyncMock()
        mock_wis_instance.transition_status = AsyncMock(return_value=updated_item)
        MockWIS.return_value = mock_wis_instance
        mock_redis_fn.return_value = None  # Redis unavailable

        result = await service.move_item(
            session,
            board_id=str(board_id),
            work_item_id=str(updated_item.id),
            column_id=str(col.id),
        )

    # Should succeed even without Redis
    assert result is updated_item


# ---------------------------------------------------------------------------
# WipLimitExceeded exception
# ---------------------------------------------------------------------------


def test_wip_limit_exceeded_message():
    exc = WipLimitExceeded("In Progress", 3, 3)
    assert "In Progress" in str(exc)
    assert "3" in str(exc)
    assert exc.wip_limit == 3
    assert exc.current_count == 3
