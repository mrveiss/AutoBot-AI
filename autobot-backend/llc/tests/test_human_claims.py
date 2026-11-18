# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for human claim/unclaim on LLC work items (GH#8223).

Mirrors the mock pattern used in test_atomic_checkout.py.
Verifies:
  1. claim_human sets assignee fields, status → IN_PROGRESS.
  2. claim_human raises CheckoutConflict when Redis key is held by another.
  3. claim_human raises CheckoutConflict when DB shows different assignee (no-Redis path).
  4. claim_human succeeds when Redis unavailable (DB-only path).
  5. claim_human raises ValueError when item not found.
  6. unclaim_human clears assignee fields and status → READY.
  7. unclaim_human raises ValueError when wrong user.
  8. unclaim_human raises ValueError when item not found.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.redis_utils import COMPARE_AND_DELETE_LUA
from llc.models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_service import CheckoutConflict, WorkItemService


def _make_item(**kwargs) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "identifier": "WI-100",
        "type": WorkItemType.TASK,
        "title": "Human task",
        "status": WorkItemStatus.READY,
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
    db_result = MagicMock()
    session.execute = AsyncMock(return_value=db_result)
    session._db_result = db_result
    return session


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.delete = AsyncMock()
    return redis


class TestHumanClaim:
    async def test_claim_sets_assignee_fields(self, service, mock_session, mock_redis):
        user_id = str(uuid.uuid4())
        company_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await service.claim_human(mock_session, str(item.id), user_id, company_id)

        assert result.assignee_user_id == uuid.UUID(user_id)
        assert result.assignee_type == "user"
        assert result.status == WorkItemStatus.IN_PROGRESS
        assert result.version == 2
        mock_redis.set.assert_called_once_with(f"llc:checkout:{item.id}", f"user:{user_id}", nx=True, ex=1800)

    async def test_claim_conflict_redis_held_by_another(self, service, mock_session, mock_redis):
        user_id = str(uuid.uuid4())
        other_value = f"user:{uuid.uuid4()}"
        item = _make_item()
        mock_redis.set.return_value = False
        mock_redis.get.return_value = other_value

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            with pytest.raises(CheckoutConflict):
                await service.claim_human(mock_session, str(item.id), user_id, str(uuid.uuid4()))

    async def test_claim_conflict_db_different_assignee_no_redis(self, service, mock_session):
        user_id = str(uuid.uuid4())
        other_user = uuid.uuid4()
        item = _make_item(assignee_user_id=other_user)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(CheckoutConflict):
                await service.claim_human(mock_session, str(item.id), user_id, str(uuid.uuid4()))

    async def test_claim_no_redis_succeeds(self, service, mock_session):
        user_id = str(uuid.uuid4())
        item = _make_item()
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            result = await service.claim_human(mock_session, str(item.id), user_id, str(uuid.uuid4()))

        assert result.assignee_user_id == uuid.UUID(user_id)

    async def test_claim_item_not_found(self, service, mock_session, mock_redis):
        mock_session._db_result.scalar_one_or_none.return_value = None

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            with pytest.raises(ValueError, match="not found"):
                await service.claim_human(mock_session, str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))
        mock_redis.eval.assert_awaited_once()  # the fence this call took, dropped while it still names the claim

    async def test_claim_idempotent_same_user(self, service, mock_session, mock_redis):
        """Same user re-claiming (Redis NX fails but same value) — should succeed."""
        user_id = str(uuid.uuid4())
        item = _make_item(assignee_user_id=uuid.UUID(user_id), assignee_type="user")
        mock_redis.set.return_value = False
        mock_redis.get.return_value = f"user:{user_id}"
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await service.claim_human(mock_session, str(item.id), user_id, str(uuid.uuid4()))
        assert result is item


class TestHumanUnclaim:
    async def test_unclaim_clears_fields_and_sets_ready(self, service, mock_session, mock_redis):
        user_id = str(uuid.uuid4())
        item = _make_item(
            assignee_user_id=uuid.UUID(user_id),
            assignee_type="user",
            status=WorkItemStatus.IN_PROGRESS,
        )
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=mock_redis),
        ):
            result = await service.unclaim_human(mock_session, str(item.id), user_id, str(uuid.uuid4()))

        assert result.assignee_user_id is None
        assert result.assignee_type is None
        assert result.status == WorkItemStatus.READY
        assert result.version == 2
        mock_redis.eval.assert_awaited_once_with(
            COMPARE_AND_DELETE_LUA, 1, f"llc:checkout:{item.id}", f"user:{user_id}"
        )  # the claim's own fence, owner-checked in one step
        mock_redis.delete.assert_not_called()

    async def test_unclaim_wrong_user_raises(self, service, mock_session):
        real_user = uuid.uuid4()
        wrong_user = str(uuid.uuid4())
        item = _make_item(assignee_user_id=real_user)
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ValueError, match="does not hold claim"):
                await service.unclaim_human(mock_session, str(item.id), wrong_user, str(uuid.uuid4()))

    async def test_unclaim_item_not_found(self, service, mock_session):
        mock_session._db_result.scalar_one_or_none.return_value = None

        with patch(
            "llc.services.work_item_service.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ValueError, match="not found"):
                await service.unclaim_human(mock_session, str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4()))


class TestClaimRespectsAgentCheckout:
    async def test_claim_refused_when_agent_holds_item_and_fence_is_gone(self, service, mock_session):
        """Fence expired / Redis down: the row lock is the authority, a live agent checkout is not overwritten."""
        agent = uuid.uuid4()
        run = str(uuid.uuid4())
        stamp = datetime.now(timezone.utc)
        item = _make_item(
            assignee_agent_id=agent,
            assignee_type="agent",
            checkout_run_id=run,
            checkout_locked_at=stamp,
            status=WorkItemStatus.IN_PROGRESS,
        )
        mock_session._db_result.scalar_one_or_none.return_value = item

        with patch("llc.services.work_item_service.get_async_redis_client", new=AsyncMock(return_value=None)):
            with pytest.raises(CheckoutConflict):
                await service.claim_human(mock_session, str(item.id), str(uuid.uuid4()), str(uuid.uuid4()))

        assert (item.assignee_agent_id, item.assignee_user_id, item.checkout_run_id) == (agent, None, run)
        assert item.version == 1 and item.checkout_locked_at == stamp

    async def test_refusal_drops_only_a_fence_this_call_took(self, service, mock_session, mock_redis):
        item = _make_item(
            assignee_agent_id=uuid.uuid4(), checkout_run_id="r", checkout_locked_at=datetime.now(timezone.utc)
        )
        mock_session._db_result.scalar_one_or_none.return_value = item
        mock_redis.set.return_value = False  # someone else's fence stands
        mock_redis.get.return_value = None
        with patch("llc.services.work_item_service.get_async_redis_client", new=AsyncMock(return_value=mock_redis)):
            with pytest.raises(CheckoutConflict):
                await service.claim_human(mock_session, str(item.id), str(uuid.uuid4()), str(uuid.uuid4()))
        mock_redis.eval.assert_not_awaited()
        mock_redis.delete.assert_not_awaited()
