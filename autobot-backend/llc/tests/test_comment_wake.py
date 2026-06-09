# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for comment-driven agent wake (GH#9624)."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import HeartbeatInvocationSource, LLCRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.work_item import LLCWorkItemComment
from ..services.comment_wake_service import CommentWakeService


@pytest.fixture
def mock_agent_org_node():
    """Mock agent_org_nodes query result."""
    return {
        "adapter_type": "claude_code",
        "adapter_config": {"model": "claude-sonnet-4-6"},
        "context_mode": "fat",
        "heartbeat_enabled": True,
    }


@pytest.fixture
def comment_wake_service():
    return CommentWakeService()


@pytest.mark.asyncio
async def test_comment_triggers_wake_for_claude_code_agent(
    mock_session: AsyncSession,
    comment_wake_service: CommentWakeService,
    mock_agent_org_node: dict,
):
    """Test that commenting on a work item triggers a wake for claude_code agent."""
    work_item_id = uuid.uuid4()
    company_id = uuid.uuid4()
    assignee_agent_id = "test-agent"
    comment_id = uuid.uuid4()

    # Mock work item query
    work_item_result = MagicMock()
    work_item_result.first.return_value = MagicMock(
        assignee_agent_id=assignee_agent_id,
        company_id=company_id,
    )

    # Mock agent query
    agent_result = MagicMock()
    agent_result.mappings.return_value.first.return_value = mock_agent_org_node

    # Mock active run query (no active runs)
    active_run_result = MagicMock()
    active_run_result.scalar_one_or_none.return_value = None

    # Mock comment query
    comment_result = MagicMock()
    comment = LLCWorkItemComment(
        id=comment_id,
        company_id=company_id,
        work_item_id=work_item_id,
        body="Test comment body",
        author_user_id=uuid.uuid4(),
    )
    comment_result.scalar_one_or_none.return_value = comment

    mock_session.execute = AsyncMock(
        side_effect=[
            work_item_result,
            agent_result,
            active_run_result,
            comment_result,
        ]
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Trigger wake
    result = await comment_wake_service.trigger_comment_wake(
        mock_session,
        work_item_id=str(work_item_id),
        comment_id=str(comment_id),
    )

    # Assertions
    assert result is not None
    run_id, agent_config, context = result

    assert isinstance(run_id, uuid.UUID)
    assert agent_config["agent_id"] == assignee_agent_id
    assert agent_config["adapter_type"] == "claude_code"
    assert context["wake_reason"] == "work_item_commented"
    assert context["wake_comment_id"] == str(comment_id)
    assert context["comment_body"] == "Test comment body"

    # Verify run was created
    mock_session.add.assert_called_once()
    added_run = mock_session.add.call_args[0][0]
    assert isinstance(added_run, LLCHeartbeatRun)
    assert added_run.agent_id == assignee_agent_id
    assert added_run.invocation_source == HeartbeatInvocationSource.WORK_ITEM_COMMENTED.value
    assert added_run.status == LLCRunStatus.QUEUED.value
    assert added_run.context_snapshot == context


@pytest.mark.asyncio
async def test_comment_wake_skips_non_claude_code_agent(
    mock_session: AsyncSession,
    comment_wake_service: CommentWakeService,
):
    """Test that wake is skipped for non-claude_code adapters."""
    work_item_id = uuid.uuid4()
    assignee_agent_id = "test-agent"
    comment_id = uuid.uuid4()

    work_item_result = MagicMock()
    work_item_result.first.return_value = MagicMock(
        assignee_agent_id=assignee_agent_id,
        company_id=uuid.uuid4(),
    )

    # Mock agent with different adapter type
    agent_result = MagicMock()
    agent_result.mappings.return_value.first.return_value = {
        "adapter_type": "http",
        "adapter_config": {},
        "context_mode": "fat",
        "heartbeat_enabled": True,
    }

    mock_session.execute = AsyncMock(side_effect=[work_item_result, agent_result])

    result = await comment_wake_service.trigger_comment_wake(
        mock_session,
        work_item_id=str(work_item_id),
        comment_id=str(comment_id),
    )

    assert result is None


@pytest.mark.asyncio
async def test_comment_wake_dedup_prevents_parallel_runs(
    mock_session: AsyncSession,
    comment_wake_service: CommentWakeService,
    mock_agent_org_node: dict,
):
    """Test that dedup guard prevents parallel runs when one is already active."""
    work_item_id = uuid.uuid4()
    company_id = uuid.uuid4()
    assignee_agent_id = "test-agent"
    comment_id = uuid.uuid4()

    work_item_result = MagicMock()
    work_item_result.first.return_value = MagicMock(
        assignee_agent_id=assignee_agent_id,
        company_id=company_id,
    )

    agent_result = MagicMock()
    agent_result.mappings.return_value.first.return_value = mock_agent_org_node

    # Mock active run query (has an active run)
    active_run_result = MagicMock()
    active_run = LLCHeartbeatRun(
        id=uuid.uuid4(),
        company_id=company_id,
        agent_id=assignee_agent_id,
        invocation_source=HeartbeatInvocationSource.SCHEDULER.value,
        status=LLCRunStatus.RUNNING.value,
    )
    active_run_result.scalar_one_or_none.return_value = active_run

    mock_session.execute = AsyncMock(
        side_effect=[
            work_item_result,
            agent_result,
            active_run_result,
        ]
    )
    mock_session.add = MagicMock()

    result = await comment_wake_service.trigger_comment_wake(
        mock_session,
        work_item_id=str(work_item_id),
        comment_id=str(comment_id),
    )

    # Should return None due to dedup guard
    assert result is None
    # Should not create a new run
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_comment_wake_skips_when_no_assignee(
    mock_session: AsyncSession,
    comment_wake_service: CommentWakeService,
):
    """Test that wake is skipped when work item has no assignee."""
    work_item_id = uuid.uuid4()
    comment_id = uuid.uuid4()

    work_item_result = MagicMock()
    work_item_result.first.return_value = MagicMock(
        assignee_agent_id=None,  # No assignee
        company_id=uuid.uuid4(),
    )

    mock_session.execute = AsyncMock(side_effect=[work_item_result])

    result = await comment_wake_service.trigger_comment_wake(
        mock_session,
        work_item_id=str(work_item_id),
        comment_id=str(comment_id),
    )

    assert result is None


@pytest.mark.asyncio
async def test_comment_wake_context_includes_comment_metadata(
    mock_session: AsyncSession,
    comment_wake_service: CommentWakeService,
    mock_agent_org_node: dict,
):
    """Test that wake context includes full comment metadata."""
    work_item_id = uuid.uuid4()
    company_id = uuid.uuid4()
    assignee_agent_id = "test-agent"
    comment_id = uuid.uuid4()
    author_agent_id = uuid.uuid4()

    work_item_result = MagicMock()
    work_item_result.first.return_value = MagicMock(
        assignee_agent_id=assignee_agent_id,
        company_id=company_id,
    )

    agent_result = MagicMock()
    agent_result.mappings.return_value.first.return_value = mock_agent_org_node

    active_run_result = MagicMock()
    active_run_result.scalar_one_or_none.return_value = None

    comment_result = MagicMock()
    comment = LLCWorkItemComment(
        id=comment_id,
        company_id=company_id,
        work_item_id=work_item_id,
        body="Test comment with detailed info",
        author_agent_id=author_agent_id,
        author_user_id=None,
    )
    comment_result.scalar_one_or_none.return_value = comment

    mock_session.execute = AsyncMock(
        side_effect=[
            work_item_result,
            agent_result,
            active_run_result,
            comment_result,
        ]
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    result = await comment_wake_service.trigger_comment_wake(
        mock_session,
        work_item_id=str(work_item_id),
        comment_id=str(comment_id),
    )

    assert result is not None
    _, _, context = result

    assert context["wake_reason"] == "work_item_commented"
    assert context["wake_comment_id"] == str(comment_id)
    assert context["work_item_id"] == str(work_item_id)
    assert context["comment_body"] == "Test comment with detailed info"
    assert context["comment_author_agent_id"] == str(author_agent_id)
    assert context["comment_author_user_id"] is None
    assert "comment_created_at" in context
