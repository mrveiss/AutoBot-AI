"""Tests for LLC WorkItemService CRUD and status transitions (GH#8213)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_service import (
    InvalidTransition,
    WorkItemService,
)


def _make_item(**kwargs) -> LLCWorkItem:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "identifier": "WI-001",
        "type": WorkItemType.TASK,
        "title": "Test task",
        "status": WorkItemStatus.BACKLOG,
        "priority": WorkItemPriority.MEDIUM,
        "version": 1,
        "labels": [],
        "checkout_run_id": None,
        "checkout_locked_at": None,
        "assignee_agent_id": None,
        "assignee_user_id": None,
        "assignee_type": None,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(kwargs)
    item = MagicMock(spec=LLCWorkItem)
    for k, v in defaults.items():
        setattr(item, k, v)
    return item


@pytest.fixture
def service():
    return WorkItemService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    # AsyncMock.return_value defaults to AsyncMock; use a plain MagicMock so
    # synchronous methods like scalar_one_or_none() return values, not coroutines.
    _db_result = MagicMock()
    session.execute = AsyncMock(return_value=_db_result)
    session._db_result = _db_result
    return session


class TestCreate:
    async def test_create_sets_identifier_and_flushes(self, service, mock_session):
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-1")):
            mock_session.flush = AsyncMock()
            # session.add captures the item
            captured = {}

            def _add(obj):
                captured["item"] = obj

            mock_session.add.side_effect = _add
            item = await service.create(
                mock_session,
                company_id=str(uuid.uuid4()),
                type=WorkItemType.TASK,
                title="My task",
                priority=WorkItemPriority.HIGH,
            )
        assert item.identifier == "PRJ-1"
        assert item.title == "My task"
        assert item.priority == WorkItemPriority.HIGH
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    async def test_create_sets_parent_id(self, service, mock_session):
        parent_id = str(uuid.uuid4())
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-2")):
            with patch.object(service, "get", new=AsyncMock(return_value=None)):
                item = await service.create(
                    mock_session,
                    company_id=str(uuid.uuid4()),
                    type=WorkItemType.SUBTASK,
                    title="Child",
                    parent_id=parent_id,
                )
        assert str(item.parent_id) == parent_id

    async def test_create_inherits_goal_id_from_parent(self, service, mock_session):
        """Sub-task inherits parent's goal_id when none is explicitly provided (GH#6469)."""
        parent_id = str(uuid.uuid4())
        inherited_goal_id = uuid.uuid4()
        parent_item = _make_item(goal_id=inherited_goal_id)
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-3")):
            with patch.object(service, "get", new=AsyncMock(return_value=parent_item)):
                item = await service.create(
                    mock_session,
                    company_id=str(uuid.uuid4()),
                    type=WorkItemType.SUBTASK,
                    title="Child with inherited goal",
                    parent_id=parent_id,
                )
        assert item.goal_id == inherited_goal_id

    async def test_create_explicit_goal_id_overrides_parent(self, service, mock_session):
        """Explicit goal_id takes precedence over parent's goal_id (GH#6469)."""
        parent_id = str(uuid.uuid4())
        explicit_goal_id = str(uuid.uuid4())
        parent_item = _make_item(goal_id=uuid.uuid4())
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-4")):
            with patch.object(service, "get", new=AsyncMock(return_value=parent_item)):
                item = await service.create(
                    mock_session,
                    company_id=str(uuid.uuid4()),
                    type=WorkItemType.SUBTASK,
                    title="Child with explicit goal",
                    parent_id=parent_id,
                    goal_id=explicit_goal_id,
                )
        assert str(item.goal_id) == explicit_goal_id

    async def test_create_no_goal_when_parent_has_none(self, service, mock_session):
        """No goal_id is set when parent work item also has no goal (GH#6469)."""
        parent_id = str(uuid.uuid4())
        parent_item = _make_item(goal_id=None)
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-5")):
            with patch.object(service, "get", new=AsyncMock(return_value=parent_item)):
                item = await service.create(
                    mock_session,
                    company_id=str(uuid.uuid4()),
                    type=WorkItemType.SUBTASK,
                    title="Child without goal",
                    parent_id=parent_id,
                )
        assert item.goal_id is None


class TestStatusTransitions:
    async def test_valid_backlog_to_ready(self, service, mock_session):
        item = _make_item(status=WorkItemStatus.BACKLOG)
        mock_session._db_result.scalar_one_or_none.return_value = item
        result = await service.transition_status(mock_session, str(item.id), WorkItemStatus.READY)
        assert result.status == WorkItemStatus.READY

    async def test_valid_in_progress_to_done(self, service, mock_session):
        item = _make_item(status=WorkItemStatus.IN_PROGRESS)
        mock_session._db_result.scalar_one_or_none.return_value = item
        result = await service.transition_status(mock_session, str(item.id), WorkItemStatus.DONE)
        assert result.status == WorkItemStatus.DONE
        assert result.completed_at is not None

    async def test_invalid_done_to_backlog_raises(self, service, mock_session):
        item = _make_item(status=WorkItemStatus.DONE)
        mock_session._db_result.scalar_one_or_none.return_value = item
        with pytest.raises(InvalidTransition):
            await service.transition_status(mock_session, str(item.id), WorkItemStatus.BACKLOG)

    async def test_invalid_cancelled_to_in_progress_raises(self, service, mock_session):
        item = _make_item(status=WorkItemStatus.CANCELLED)
        mock_session._db_result.scalar_one_or_none.return_value = item
        with pytest.raises(InvalidTransition):
            await service.transition_status(mock_session, str(item.id), WorkItemStatus.IN_PROGRESS)

    async def test_not_found_raises_value_error(self, service, mock_session):
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.transition_status(mock_session, str(uuid.uuid4()), WorkItemStatus.READY)

    async def test_transition_to_cancelled_sets_cancelled_at(self, service, mock_session):
        item = _make_item(status=WorkItemStatus.IN_PROGRESS)
        mock_session._db_result.scalar_one_or_none.return_value = item
        result = await service.transition_status(mock_session, str(item.id), WorkItemStatus.CANCELLED)
        assert result.cancelled_at is not None

    async def test_version_bumped_on_every_transition(self, service, mock_session):
        item = _make_item(status=WorkItemStatus.BACKLOG, version=3)
        mock_session._db_result.scalar_one_or_none.return_value = item
        await service.transition_status(mock_session, str(item.id), WorkItemStatus.READY)
        assert item.version == 4


class TestListByProject:
    async def test_returns_all_for_company(self, service, mock_session):
        items = [_make_item(), _make_item()]
        mock_session._db_result.scalars.return_value.all.return_value = items
        result = await service.list_by_project(mock_session, company_id=str(uuid.uuid4()))
        assert len(result) == 2
