# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Comment-driven agent wake (GH#9624), now a caller of the one dispatcher (#19582).

The comment rules stay here: an agent assignee is required, the commenter is not the
assignee, and the comment travels as context. The two gates the service used to have
(``adapter_type == "claude_code"`` and ``heartbeat_enabled``) are gone -- the
``adapter`` parametrisation below is the regression test for that.
"""

import uuid

import pytest
from sqlalchemy import select

from llc.models.enums import HeartbeatInvocationSource, LLCRunStatus
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.models.work_item import LLCWorkItemComment
from llc.services.comment_wake_service import CommentWakeService
from llc.tests.test_event_wakes_19582 import _COMPANY, _USER, _agent, _item, _tick_run, dispatched, factory

__all__ = ["dispatched", "factory"]  # pytest fixtures, imported for this module's tests


async def _comment_on(
    factory, item_id: uuid.UUID, body: str = "Test comment body", **author
) -> uuid.UUID:  # noqa: ANN001
    async with factory() as session:
        comment = LLCWorkItemComment(id=uuid.uuid4(), company_id=_COMPANY, work_item_id=item_id, body=body, **author)
        session.add(comment)
        await session.commit()
        return comment.id


async def _wake(factory, item_id: uuid.UUID, comment_id: uuid.UUID):  # noqa: ANN001, ANN202
    async with factory() as session:
        run_id = await CommentWakeService().trigger_comment_wake(session, str(item_id), str(comment_id))
        await session.commit()
    return run_id


async def _assigned_item(factory, node) -> uuid.UUID:  # noqa: ANN001
    """An item assigned to *node* whose assignment wake has already finished."""
    item_id = await _item(factory, assignee=str(node.id))
    async with factory() as session:
        for run in (await session.execute(select(LLCHeartbeatRun))).scalars():
            run.status = LLCRunStatus.COMPLETED.value
        await session.commit()
    return item_id


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", [None, "claude_code", "claude_code_subscription"])
async def test_a_comment_wakes_the_assignee_whatever_its_adapter(factory, dispatched, adapter) -> None:  # noqa: ANN001
    node = await _agent(factory, adapter=adapter)
    item_id = await _assigned_item(factory, node)
    comment_id = await _comment_on(factory, item_id, author_user_id=_USER)
    run_id = await _wake(factory, item_id, comment_id)
    assert run_id is not None
    async with factory() as session:
        run = await session.get(LLCHeartbeatRun, run_id)
    assert run.agent_id == node.agent_id  # keyed by the slug, not the PK (#10032)
    assert run.invocation_source == HeartbeatInvocationSource.WORK_ITEM_COMMENTED.value
    assert [agent["adapter_type"] for agent, rid, _ in dispatched if rid == run_id] == [adapter]


@pytest.mark.asyncio
async def test_the_wake_carries_the_comment(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _assigned_item(factory, node)
    other_agent = uuid.uuid4()
    comment_id = await _comment_on(factory, item_id, "detailed info", author_agent_id=other_agent)
    run_id = await _wake(factory, item_id, comment_id)
    (context,) = [ctx for _, rid, ctx in dispatched if rid == run_id]
    assert context["wake_reason"] == "work_item_commented"
    assert context["wake_comment_id"] == str(comment_id)
    assert context["work_item_id"] == str(item_id)
    assert context["comment_body"] == "detailed info"
    assert context["comment_author_agent_id"] == str(other_agent)
    assert context["comment_author_user_id"] is None
    assert "comment_created_at" in context


@pytest.mark.asyncio
async def test_no_assignee_no_wake(factory, dispatched) -> None:  # noqa: ANN001
    item_id = await _item(factory)
    assert await _wake(factory, item_id, await _comment_on(factory, item_id, author_user_id=_USER)) is None
    assert dispatched == []


@pytest.mark.asyncio
async def test_an_active_run_is_not_doubled(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _assigned_item(factory, node)
    await _tick_run(factory, node, LLCRunStatus.RUNNING.value)
    assert await _wake(factory, item_id, await _comment_on(factory, item_id, author_user_id=_USER)) is None


@pytest.mark.asyncio
async def test_an_unknown_comment_wakes_no_one(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    item_id = await _assigned_item(factory, node)
    assert await _wake(factory, item_id, uuid.uuid4()) is None
