# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person moves their own task freely; everyone else keeps the transition rules (#20508)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from llc.models.enums import WorkItemStatus
from llc.services.work_item_service import InvalidTransition, WorkItemService

_ME, _OTHER = uuid.uuid4(), uuid.uuid4()
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _item(status: WorkItemStatus, *, created_by=None, assignee=None, reviewer=None) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(), company_id=uuid.uuid4(), status=status, created_by_user_id=created_by,
        assignee_user_id=assignee, reviewer_user_id=reviewer, completed_at=_NOW, cancelled_at=None, started_at=_NOW,
        checkout_run_id=uuid.uuid4(), checkout_locked_at=_NOW, version=1,
    )  # fmt: skip


async def _move(item: MagicMock, new_status: WorkItemStatus, acting_user) -> MagicMock:
    session = MagicMock(flush=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: item))
    return await WorkItemService(activity_log=MagicMock()).transition_status(
        session, str(item.id), new_status, acting_user=acting_user
    )


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
