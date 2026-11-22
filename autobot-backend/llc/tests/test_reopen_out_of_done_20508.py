# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``done`` has a reopen edge, recorded in the activity log; any other move out of it says why it is refused (#20508).

Owner decision 2026-11-21: ``done`` -> ``todo`` / ``in_progress`` is allowed. There is no ``todo`` status: the
backlog's "ready" is the work-waiting-to-be-picked-up state, so the edge is ``done`` -> ``ready``.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.api._common import refused_transition
from llc.models.enums import ActivityEventType, WorkItemStatus, WorkItemType
from llc.services import after_commit
from llc.services.work_item_service import _ALLOWED_TRANSITIONS, InvalidTransition, WorkItemService
from testkit.fake_async_session import FakeAsyncSession

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_SOMEONE_ELSE = uuid.uuid4()


@pytest.fixture(autouse=True)
def _no_redis():
    with patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=None)):
        yield


def _done_item() -> MagicMock:
    """A finished task that is nobody's own: the move goes through the transition table, not the own-task rule."""
    return MagicMock(
        id=uuid.uuid4(), company_id=uuid.uuid4(), type=WorkItemType.TASK, status=WorkItemStatus.DONE,
        created_by_user_id=uuid.uuid4(), assignee_user_id=None, reviewer_user_id=None, completed_at=_NOW,
        cancelled_at=None, started_at=_NOW, checkout_run_id=None, checkout_locked_at=None, version=1,
    )  # fmt: skip


async def _move(item: MagicMock, new_status: WorkItemStatus, acting_user, log: MagicMock) -> MagicMock:
    session = FakeAsyncSession(results=[[item]])
    moved = await WorkItemService(activity_log=log).transition_status(
        session, str(item.id), new_status, acting_user=acting_user
    )
    await asyncio.gather(*after_commit.after_commit_tasks)
    return moved


def test_done_reopens_to_ready_and_in_progress_only() -> None:
    assert _ALLOWED_TRANSITIONS[WorkItemStatus.DONE] == {WorkItemStatus.READY, WorkItemStatus.IN_PROGRESS}


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [WorkItemStatus.READY, WorkItemStatus.IN_PROGRESS])
@pytest.mark.parametrize("acting_user", [_SOMEONE_ELSE, None], ids=["a-person", "no-verified-person"])
async def test_a_reopen_is_allowed_clears_completion_and_is_recorded(target, acting_user) -> None:
    log = MagicMock(record=AsyncMock())
    item = await _move(_done_item(), target, acting_user, log)

    assert item.status == target
    assert item.completed_at is None, "a reopened task is no longer completed"
    log.record.assert_awaited_once()
    row = log.record.await_args.kwargs
    assert row["event_type"] == ActivityEventType.WORK_ITEM_STATUS_CHANGED
    assert row["entity_id"] == str(item.id) and row["company_id"] == str(item.company_id)
    assert row["before"] == {"status": "done"}
    assert row["after"] == {"status": target.value, "reopened": True}
    assert row["actor_id"] == (str(acting_user) if acting_user else None), "the verified person, else the system"


@pytest.mark.asyncio
async def test_an_ordinary_move_writes_no_reopen_row() -> None:
    log = MagicMock(record=AsyncMock())
    item = _done_item()
    item.status = WorkItemStatus.READY
    await _move(item, WorkItemStatus.IN_PROGRESS, _SOMEONE_ELSE, log)
    log.record.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [WorkItemStatus.BLOCKED, WorkItemStatus.CANCELLED, WorkItemStatus.BACKLOG])
async def test_a_move_still_refused_says_why_and_writes_nothing(target) -> None:
    log = MagicMock(record=AsyncMock())
    item = _done_item()
    with pytest.raises(InvalidTransition) as refused:
        await _move(item, target, _SOMEONE_ELSE, log)

    assert item.status == WorkItemStatus.DONE and item.completed_at == _NOW
    log.record.assert_not_awaited()
    http = refused_transition(refused.value)
    assert http.status_code == 409
    assert "'done'" in http.detail and f"'{target.value}'" in http.detail, "the reason names both statuses"
