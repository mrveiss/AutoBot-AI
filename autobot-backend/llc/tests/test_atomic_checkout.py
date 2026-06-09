# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for atomic checkout concurrency (GH#8213).

Verifies:
  1. First checkout succeeds and sets checkout fields.
  2. Concurrent checkout by a different agent raises CheckoutConflict (Redis fence).
  3. Re-checkout by the same agent is idempotent.
  4. Release clears checkout fields and Redis key.
  5. Release by wrong agent raises ValueError.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_service import CheckoutConflict, WorkItemService


def _make_item(**kwargs) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "identifier": "WI-099",
        "type": WorkItemType.TASK,
        "title": "Concurrent task",
        "status": WorkItemStatus.READY,
        "priority": WorkItemPriority.HIGH,
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
    _db_result = MagicMock()
    session.execute = AsyncMock(return_value=_db_result)
    session._db_result = _db_result
    return session


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)  # NX acquire succeeds by default
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis


class TestAtomicCheckout:
    async def test_checkout_sets_lock_fields(self, service, mock_session, mock_redis):
        agent_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await service.checkout(mock_session, str(item.id), agent_id, run_id=run_id)

        assert result.checkout_run_id == run_id
        assert result.checkout_locked_at is not None
        assert str(result.assignee_agent_id) == agent_id
        assert result.version == 2
        mock_redis.set.assert_called_once_with(f"llc:checkout:{item.id}", agent_id, nx=True, ex=1800)

    async def test_checkout_conflict_different_agent(self, service, mock_session, mock_redis):
        """Redis NX returns False (key exists for another agent) → CheckoutConflict."""
        agent_id = str(uuid.uuid4())
        other_agent = str(uuid.uuid4())
        item = _make_item()
        mock_redis.set.return_value = False  # NX acquire fails
        mock_redis.get.return_value = other_agent  # held by other agent

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            with pytest.raises(CheckoutConflict):
                await service.checkout(mock_session, str(item.id), agent_id)

    async def test_checkout_same_agent_idempotent(self, service, mock_session, mock_redis):
        """NX returns False but existing key belongs to same agent — allowed."""
        agent_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        item = _make_item(
            checkout_run_id=run_id,
            assignee_agent_id=uuid.UUID(agent_id),
        )
        mock_redis.set.return_value = False  # key already set
        mock_redis.get.return_value = agent_id  # same agent holds it
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await service.checkout(mock_session, str(item.id), agent_id, run_id=run_id)
        # Should not raise; item returned
        assert result is item

    async def test_checkout_without_redis_uses_db_only(self, service, mock_session):
        """When Redis is unavailable, checkout falls through to DB lock only."""
        agent_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            result = await service.checkout(mock_session, str(item.id), agent_id)

        assert result.assignee_agent_id == uuid.UUID(agent_id)

    async def test_checkout_item_not_found(self, service, mock_session, mock_redis):
        mock_session.execute.return_value.scalar_one_or_none.return_value = None
        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            with pytest.raises(ValueError, match="not found"):
                await service.checkout(mock_session, str(uuid.uuid4()), str(uuid.uuid4()))


class TestRelease:
    async def test_release_clears_checkout_fields(self, service, mock_session):
        """Service clears DB checkout fields; Redis deletion happens in the route after commit."""
        agent_id = str(uuid.uuid4())
        item = _make_item(
            checkout_run_id="run-123",
            assignee_agent_id=uuid.UUID(agent_id),
        )
        mock_session._db_result.scalar_one_or_none.return_value = item

        result = await service.release(mock_session, str(item.id), agent_id)

        assert result.checkout_run_id is None
        assert result.checkout_locked_at is None
        mock_session.flush.assert_called_once()

    async def test_release_wrong_agent_raises(self, service, mock_session):
        real_agent = str(uuid.uuid4())
        wrong_agent = str(uuid.uuid4())
        item = _make_item(assignee_agent_id=uuid.UUID(real_agent))
        mock_session._db_result.scalar_one_or_none.return_value = item

        with pytest.raises(ValueError, match="does not hold checkout"):
            await service.release(mock_session, str(item.id), wrong_agent)
