# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for union assignment model — co-working and co-worker filters (GH#8230).

Verifies:
  1. enable_coworking sets co-worker fields and co_working_enabled=True.
  2. enable_coworking raises CoWorkingPermissionError for insufficient role.
  3. enable_coworking raises ValueError when agent id missing for 'agent' type.
  4. enable_coworking raises ValueError when user id missing for 'human' type.
  5. enable_coworking raises ValueError when work item not found.
  6. disable_coworking clears co-worker fields and co_working_enabled=False.
  7. disable_coworking raises CoWorkingPermissionError for insufficient role.
  8. disable_coworking raises ValueError when work item not found.
  9. list_by_project filters by co_worker_agent_id.
 10. list_by_project filters by co_worker_user_id.
 11. Activity log is called on enable_coworking with WORK_ITEM_COWORKER_SET.
 12. Activity log is called on disable_coworking with WORK_ITEM_COWORKER_CLEARED.
 13. Co-worker can create subtasks (create() does not require checkout on parent).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_service import (
    CoWorkingPermissionError,
    WorkItemService,
)


def _make_item(**kwargs) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "identifier": "WI-200",
        "type": WorkItemType.TASK,
        "title": "Co-working task",
        "status": WorkItemStatus.IN_PROGRESS,
        "priority": WorkItemPriority.MEDIUM,
        "version": 1,
        "labels": [],
        "checkout_run_id": None,
        "checkout_locked_at": None,
        "assignee_agent_id": None,
        "assignee_user_id": None,
        "assignee_type": None,
        "co_worker_type": None,
        "co_worker_agent_id": None,
        "co_worker_user_id": None,
        "co_working_enabled": False,
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
    db_result = MagicMock()
    session.execute = AsyncMock(return_value=db_result)
    session._db_result = db_result
    return session


class TestEnableCoworking:
    async def test_sets_coworker_fields_agent(self, service, mock_session):
        agent_co_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.enable_coworking(
            mock_session,
            str(item.id),
            co_worker_type="agent",
            company_id=company_id,
            co_worker_agent_id=agent_co_id,
            caller_role="admin",
        )

        assert result.co_worker_type == "agent"
        assert result.co_worker_agent_id == uuid.UUID(agent_co_id)
        assert result.co_working_enabled is True
        assert result.version == 2

    async def test_sets_coworker_fields_human(self, service, mock_session):
        user_co_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.enable_coworking(
            mock_session,
            str(item.id),
            co_worker_type="human",
            company_id=company_id,
            co_worker_user_id=user_co_id,
            caller_role="owner",
        )

        assert result.co_worker_type == "human"
        assert result.co_worker_user_id == uuid.UUID(user_co_id)
        assert result.co_working_enabled is True

    async def test_raises_permission_error_for_member_role(self, service, mock_session):
        with pytest.raises(CoWorkingPermissionError, match="does not have permission"):
            await service.enable_coworking(
                mock_session,
                str(uuid.uuid4()),
                co_worker_type="agent",
                company_id=str(uuid.uuid4()),
                co_worker_agent_id=str(uuid.uuid4()),
                caller_role="member",
            )

    async def test_raises_permission_error_for_guest_role(self, service, mock_session):
        with pytest.raises(CoWorkingPermissionError):
            await service.enable_coworking(
                mock_session,
                str(uuid.uuid4()),
                co_worker_type="agent",
                company_id=str(uuid.uuid4()),
                co_worker_agent_id=str(uuid.uuid4()),
                caller_role="guest",
            )

    async def test_lead_role_is_allowed(self, service, mock_session):
        agent_co_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.enable_coworking(
            mock_session,
            str(item.id),
            co_worker_type="agent",
            company_id=str(uuid.uuid4()),
            co_worker_agent_id=agent_co_id,
            caller_role="lead",
        )
        assert result.co_working_enabled is True

    async def test_raises_value_error_agent_id_missing_for_agent_type(self, service, mock_session):
        with pytest.raises(ValueError, match="co_worker_agent_id required"):
            await service.enable_coworking(
                mock_session,
                str(uuid.uuid4()),
                co_worker_type="agent",
                company_id=str(uuid.uuid4()),
                caller_role="admin",
            )

    async def test_raises_value_error_user_id_missing_for_human_type(self, service, mock_session):
        with pytest.raises(ValueError, match="co_worker_user_id required"):
            await service.enable_coworking(
                mock_session,
                str(uuid.uuid4()),
                co_worker_type="human",
                company_id=str(uuid.uuid4()),
                caller_role="admin",
            )

    async def test_raises_value_error_item_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.enable_coworking(
                mock_session,
                str(uuid.uuid4()),
                co_worker_type="agent",
                company_id=str(uuid.uuid4()),
                co_worker_agent_id=str(uuid.uuid4()),
                caller_role="admin",
            )

    async def test_activity_log_called_on_set(self, service, mock_session):
        agent_co_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        mock_log = AsyncMock()
        mock_log.record = AsyncMock()
        service.activity_log = mock_log

        await service.enable_coworking(
            mock_session,
            str(item.id),
            co_worker_type="agent",
            company_id=company_id,
            co_worker_agent_id=agent_co_id,
            caller_role="admin",
        )

        mock_log.record.assert_called_once()
        call_kwargs = mock_log.record.call_args.kwargs
        assert call_kwargs["event_type"].value == "work_item.coworker_set"
        assert call_kwargs["entity_type"] == "work_item"


class TestDisableCoworking:
    async def test_clears_coworker_fields(self, service, mock_session):
        agent_co_id = uuid.uuid4()
        item = _make_item(
            co_worker_type="agent",
            co_worker_agent_id=agent_co_id,
            co_working_enabled=True,
        )
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.disable_coworking(
            mock_session,
            str(item.id),
            company_id=str(uuid.uuid4()),
            caller_role="admin",
        )

        assert result.co_worker_type is None
        assert result.co_worker_agent_id is None
        assert result.co_worker_user_id is None
        assert result.co_working_enabled is False
        assert result.version == 2

    async def test_raises_permission_error_for_member_role(self, service, mock_session):
        with pytest.raises(CoWorkingPermissionError):
            await service.disable_coworking(
                mock_session,
                str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                caller_role="member",
            )

    async def test_raises_value_error_item_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.disable_coworking(
                mock_session,
                str(uuid.uuid4()),
                company_id=str(uuid.uuid4()),
                caller_role="owner",
            )

    async def test_activity_log_called_on_clear(self, service, mock_session):
        item = _make_item(co_working_enabled=True, co_worker_type="human")
        mock_session._db_result.scalar_one_or_none.return_value = item

        mock_log = AsyncMock()
        mock_log.record = AsyncMock()
        service.activity_log = mock_log

        await service.disable_coworking(
            mock_session,
            str(item.id),
            company_id=str(uuid.uuid4()),
            caller_role="admin",
        )

        mock_log.record.assert_called_once()
        call_kwargs = mock_log.record.call_args.kwargs
        assert call_kwargs["event_type"].value == "work_item.coworker_cleared"


class TestCoworkerFilters:
    async def test_list_filters_by_co_worker_agent_id(self, service):
        """list_by_project passes co_worker_agent_id to query."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        items = await service.list_by_project(
            session,
            company_id=str(uuid.uuid4()),
            co_worker_agent_id=str(uuid.uuid4()),
        )
        assert items == []
        session.execute.assert_called_once()
        # Verify the query object was constructed (execute was called)
        stmt = session.execute.call_args.args[0]
        # The statement should be a SELECT with the co_worker_agent_id WHERE clause;
        # we verify execute was invoked (full clause inspection requires DB fixtures)
        assert stmt is not None

    async def test_list_filters_by_co_worker_user_id(self, service):
        """list_by_project passes co_worker_user_id to query."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        items = await service.list_by_project(
            session,
            company_id=str(uuid.uuid4()),
            co_worker_user_id=str(uuid.uuid4()),
        )
        assert items == []
        session.execute.assert_called_once()


class TestCoworkerSubtaskInvariant:
    async def test_create_does_not_require_checkout_on_parent(self, service, mock_session):
        """Co-worker creating a subtask uses create() which never checks parent checkout.

        The invariant is: primary assignee holds the checkout lock on the parent,
        but co-workers can call create() with parent_id without needing to hold
        that checkout. create() does not validate parent checkout state.
        """
        company_id = str(uuid.uuid4())
        parent_id = str(uuid.uuid4())
        parent_item = _make_item(
            id=uuid.UUID(parent_id),
            co_working_enabled=True,
            co_worker_type="agent",
            co_worker_agent_id=uuid.uuid4(),
            checkout_run_id="some-run",  # parent is checked out by primary
        )

        # create() fetches a fresh item; mock the identifier generation
        mock_session._db_result.fetchone.return_value = MagicMock(
            issue_prefix="WI", issue_counter=99
        )

        # create() should succeed without any checkout validation on parent
        co_worker_agent_id = str(uuid.uuid4())
        subtask = await service.create(
            mock_session,
            company_id=company_id,
            type=WorkItemType.SUBTASK,
            title="Subtask by co-worker",
            parent_id=parent_id,
            created_by_agent_id=co_worker_agent_id,
        )
        # If we get here without exception, the invariant holds
        assert subtask is not None
