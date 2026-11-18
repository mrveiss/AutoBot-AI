# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A task's worktree is removed from disk only once the transition that finished it commits (#21503).

The row clearing ``workspace_dir`` is part of the transaction and rolls back with it; the removal from disk cannot,
so it waits for the commit. A transition that fails to commit must leave the workspace where it was.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from llc.models.enums import WorkItemStatus, WorkItemType
from llc.services import after_commit
from llc.services.handoff import HandoffService
from llc.services.work_item_gated_done import DoneGate
from llc.services.work_item_service import WorkItemService
from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_result import FakeResult

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


class _TxSession(FakeAsyncSession):
    """A fake whose commit and rollback also drive a real SQLAlchemy session, so its hooks fire as in production."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.sync_session = Session()
        self.sync_session.begin()

    async def commit(self) -> None:
        await super().commit()
        self.sync_session.commit()

    async def rollback(self) -> None:
        await super().rollback()
        self.sync_session.rollback()


def _item() -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(), company_id=uuid.uuid4(), type=WorkItemType.TASK, status=WorkItemStatus.IN_PROGRESS,
        created_by_user_id=None, assignee_user_id=None, assignee_agent_id=None, reviewer_user_id=None,
        completed_at=None, cancelled_at=None, started_at=_NOW, checkout_run_id=None, checkout_locked_at=None, version=1,
    )  # fmt: skip


async def _finish(new_status: WorkItemStatus, commit: bool):  # noqa: ANN202
    item, workspace = _item(), SimpleNamespace(workspace_dir="/workspaces/task")
    session = _TxSession(results=[FakeResult([item]), FakeResult([workspace])])
    ungated = DoneGate(review_gate_svc=MagicMock(requires_review=AsyncMock(return_value=(False, None))))
    removed = MagicMock()
    with (
        patch("services.task_workspace.release_workspace", removed),
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=AsyncMock()),
    ):
        service = WorkItemService(activity_log=MagicMock(record=AsyncMock()))
        await service.transition_status(session, str(item.id), new_status, done_gate=ungated)
        before_commit = removed.call_count
        await (session.commit() if commit else session.rollback())
        await asyncio.gather(*after_commit.after_commit_tasks)
    return item, workspace, removed, before_commit


@pytest.mark.parametrize("status", [WorkItemStatus.DONE, WorkItemStatus.CANCELLED], ids=["done", "cancelled"])
async def test_the_worktree_goes_when_the_transition_commits(status) -> None:
    item, workspace, removed, before_commit = await _finish(status, commit=True)
    assert before_commit == 0, "the worktree was removed before the transition committed"
    assert workspace.workspace_dir is None
    assert removed.call_count == 1 and removed.call_args.args[0] == str(item.id)


@pytest.mark.parametrize("status", [WorkItemStatus.DONE, WorkItemStatus.CANCELLED], ids=["done", "cancelled"])
async def test_the_worktree_stays_when_the_transition_does_not_commit(status) -> None:
    _item_, _workspace, removed, _before = await _finish(status, commit=False)
    removed.assert_not_called()


@pytest.mark.parametrize(("commit", "removals"), [(True, 1), (False, 0)], ids=["commit", "rollback"])
async def test_the_approve_path_removes_the_worktree_only_after_commit(commit: bool, removals: int) -> None:
    reviewer, item, workspace = uuid.uuid4(), _item(), SimpleNamespace(workspace_dir="/workspaces/task")
    item.reviewer_user_id = reviewer
    # the approve's own lock, the done path's lock, then the workspace row the release reads (#21590)
    session = _TxSession(results=[FakeResult([item]), FakeResult([item]), FakeResult([workspace])])
    removed = MagicMock()
    done_path = WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    with (
        patch("services.task_workspace.release_workspace", removed),
        patch("llc.services.handoff.get_work_item_service", return_value=done_path),
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=AsyncMock()),
    ):
        service = HandoffService(activity_log=MagicMock(record=AsyncMock()))
        await service.approve(session, str(item.id), str(reviewer), str(item.company_id))
        assert removed.call_count == 0, "the worktree was removed before the approval committed"
        await (session.commit() if commit else session.rollback())
        await asyncio.gather(*after_commit.after_commit_tasks)
    assert removed.call_count == removals
