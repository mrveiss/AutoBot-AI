# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person moves their own task freely; everyone else keeps the transition rules (#20508)."""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemStatus
from llc.services import work_item_own_task
from llc.services.work_item_service import InvalidTransition, WorkItemService
from testkit.fake_async_session import FakeAsyncSession

_ME, _OTHER = uuid.uuid4(), uuid.uuid4()
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_redis():
    with patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=None)):
        yield


def _item(status: WorkItemStatus, *, created_by=None, assignee=None, reviewer=None) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(), company_id=uuid.uuid4(), status=status, created_by_user_id=created_by,
        assignee_user_id=assignee, reviewer_user_id=reviewer, completed_at=_NOW, cancelled_at=None, started_at=_NOW,
        checkout_run_id=uuid.uuid4(), checkout_locked_at=_NOW, version=1,
    )  # fmt: skip


async def _settle() -> None:
    """Let the fence release run: it is sent after the commit, as a task (a session with no commit sends it at once)."""
    await asyncio.gather(*work_item_own_task._release_tasks)


async def _move(item: MagicMock, new_status: WorkItemStatus, acting_user) -> MagicMock:
    session = FakeAsyncSession(results=[[item]])
    moved = await WorkItemService(activity_log=MagicMock()).transition_status(
        session, str(item.id), new_status, acting_user=acting_user
    )
    await _settle()
    return moved


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["created_by", "assignee"])
async def test_a_person_moves_their_own_done_task_back_to_ready(field: str) -> None:
    item = await _move(_item(WorkItemStatus.DONE, **{field: _ME}), WorkItemStatus.READY, _ME)
    assert item.status == WorkItemStatus.READY
    assert item.completed_at is None, "it is no longer finished"
    assert item.checkout_run_id is None, "a stale checkout would keep it from any agent"


@pytest.mark.asyncio
@pytest.mark.parametrize("acting_user", [_OTHER, None], ids=["someone-else", "no-verified-person"])
async def test_anyone_else_keeps_the_transition_rules(acting_user) -> None:
    done = _item(WorkItemStatus.DONE, created_by=_ME, assignee=_ME)
    with pytest.raises(InvalidTransition):
        await _move(done, WorkItemStatus.READY, acting_user)
    assert done.status == WorkItemStatus.DONE


@pytest.mark.asyncio
async def test_a_task_with_no_owner_is_nobodys_own() -> None:
    with pytest.raises(InvalidTransition):
        await _move(_item(WorkItemStatus.DONE), WorkItemStatus.READY, _ME)


def test_past_its_reviewer_is_not_an_own_task_move() -> None:
    from llc.services.work_item_own_task import is_own_task

    item = _item(WorkItemStatus.IN_REVIEW, created_by=_ME, assignee=_ME, reviewer=_OTHER)
    assert is_own_task(item, _ME, WorkItemStatus.DONE) is False


def test_the_reviewer_who_owns_the_task_moves_it_free() -> None:
    from llc.services.work_item_own_task import is_own_task

    item = _item(WorkItemStatus.IN_REVIEW, created_by=_ME, assignee=_ME, reviewer=_ME)
    assert is_own_task(item, _ME, WorkItemStatus.DONE) is True


def test_owner_moves_other_than_review_to_done_stay_free() -> None:
    from llc.services.work_item_own_task import is_own_task

    item = _item(WorkItemStatus.IN_REVIEW, created_by=_ME, assignee=_ME, reviewer=_OTHER)
    assert is_own_task(item, _ME, WorkItemStatus.IN_PROGRESS) is True
    blocked = _item(WorkItemStatus.BLOCKED, created_by=_ME, assignee=_ME, reviewer=_OTHER)
    assert is_own_task(blocked, _ME, WorkItemStatus.IN_PROGRESS) is True, "blocked with blockers stays free"


@pytest.mark.asyncio
@pytest.mark.parametrize("acting_user", [_ME, _OTHER], ids=["owner", "another-person"])
async def test_nobody_but_the_reviewer_finishes_a_task_in_review(acting_user) -> None:
    item = _item(WorkItemStatus.IN_REVIEW, created_by=_ME, assignee=_ME)
    item.reviewer_user_id = uuid.uuid4()
    with pytest.raises(InvalidTransition):
        await _move(item, WorkItemStatus.DONE, acting_user)
    assert item.status == WorkItemStatus.IN_REVIEW


@pytest.mark.asyncio
async def test_the_reviewer_finishes_it() -> None:
    item = _item(WorkItemStatus.IN_REVIEW, created_by=_OTHER)
    item.reviewer_user_id = _ME
    assert (await _move(item, WorkItemStatus.DONE, _ME)).status == WorkItemStatus.DONE


@pytest.mark.parametrize(
    ("new_status", "field", "value"),
    [(WorkItemStatus.READY, "assignee_user_id", "user:{}"), (WorkItemStatus.DONE, "assignee_agent_id", "{}#{run}")],
)
async def test_the_fence_goes_with_the_checkout_and_only_while_it_names_the_holder(new_status, field, value) -> None:
    holder = uuid.uuid4()
    item = _item(WorkItemStatus.IN_PROGRESS, created_by=holder if field == "assignee_user_id" else None)
    item.assignee_user_id, item.assignee_agent_id = None, None
    setattr(item, field, holder)
    checkout_run = item.checkout_run_id
    redis = MagicMock()
    with (
        patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=redis)),
        patch("llc.services.work_item_own_task.delete_if_value", new=AsyncMock()) as release,
    ):
        await _move(item, new_status, holder if field == "assignee_user_id" else None)
    assert item.checkout_locked_at is None
    release.assert_awaited_once_with(redis, f"llc:checkout:{item.id}", value.format(holder, run=checkout_run))


async def test_a_move_that_keeps_the_checkout_keeps_the_fence() -> None:
    me = uuid.uuid4()
    item = _item(WorkItemStatus.READY, assignee=me)
    with patch("llc.services.work_item_own_task.delete_if_value", new=AsyncMock()) as release:
        await _move(item, WorkItemStatus.IN_PROGRESS, me)
    release.assert_not_awaited()
    assert item.checkout_locked_at == _NOW


@pytest.mark.asyncio
async def test_the_gated_done_path_drops_the_fence_too() -> None:
    agent = uuid.uuid4()
    item = _item(WorkItemStatus.IN_REVIEW)
    item.assignee_user_id, item.assignee_agent_id = None, agent
    session = FakeAsyncSession(results=[[item]])
    checkout_run = item.checkout_run_id
    redis = MagicMock()
    with (
        patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=redis)),
        patch("llc.services.work_item_own_task.delete_if_value", new=AsyncMock()) as release,
        patch("llc.services.work_item_service.audit", new=AsyncMock()),
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=AsyncMock()),
    ):
        await WorkItemService(activity_log=MagicMock()).transition_to_done(
            session, str(item.id), str(item.company_id), actor_user_id=str(uuid.uuid4()), is_board_override=True
        )
        await _settle()
    release.assert_awaited_once_with(redis, f"llc:checkout:{item.id}", f"{agent}#{checkout_run}")
