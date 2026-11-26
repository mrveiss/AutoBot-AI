# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A turn whose model keeps calling tools that do not exist stops with an honest failure (#20848)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from chat_workflow import invalid_call_abort, limits
from chat_workflow.models import LLMIterationContext


def test_the_abort_waits_for_the_limit_and_comes_after_the_reminder():
    limit = limits.INVALID_TOOL_ABORT_LIMIT
    assert not invalid_call_abort.should_abort(limit - 1)
    assert invalid_call_abort.should_abort(limit)
    assert limits.INVALID_TOOL_ABORT_LIMIT > limits.INVALID_CALL_LIMIT


@pytest.mark.asyncio
async def test_the_abort_message_ends_the_turn_and_is_audited():
    ctx = LLMIterationContext.__new__(LLMIterationContext)
    ctx.session_id, ctx.workflow_messages = "chat-1", []
    ctx.consecutive_invalid_tool_calls = limits.INVALID_TOOL_ABORT_LIMIT
    with patch.object(invalid_call_abort, "audit_log", AsyncMock(return_value=True)) as audit:
        message = await invalid_call_abort.abort_message(ctx, 3)
    assert message.content == invalid_call_abort.INVALID_TOOL_ABORT_REPLY
    assert ctx.workflow_messages == [message]
    assert audit.await_args.args[0] == "chat.invalid_tool_calls_abort"
    assert audit.await_args.kwargs["session_id"] == "chat-1"


def test_the_graph_routes_a_turn_at_the_limit_to_the_abort_node_20848():
    from chat_workflow.graph import route_after_execution

    base = {"should_continue": True, "iteration_count": 1}
    below = {**base, "consecutive_invalid_tool_calls": limits.INVALID_TOOL_ABORT_LIMIT - 1}
    at = {**base, "consecutive_invalid_tool_calls": limits.INVALID_TOOL_ABORT_LIMIT}
    assert route_after_execution(below) == "generate_response"
    assert route_after_execution(at) == "abort_invalid_tools"


@pytest.mark.asyncio
async def test_the_graph_abort_node_streams_and_audits_the_same_stop_20848():
    streamed = []
    state = {
        "session_id": "chat-2",
        "iteration_count": 4,
        "workflow_messages": [],
        "consecutive_invalid_tool_calls": limits.INVALID_TOOL_ABORT_LIMIT,
    }
    config = {"configurable": {"stream_callback": streamed.append}}
    with patch.object(invalid_call_abort, "audit_log", AsyncMock(return_value=True)) as audit:
        update = await invalid_call_abort.abort_invalid_tools(state, config)
    assert update["workflow_messages"] == streamed
    assert streamed[0]["content"] == invalid_call_abort.INVALID_TOOL_ABORT_REPLY
    assert update["should_continue"] is False
    assert audit.await_args.args[0] == "chat.invalid_tool_calls_abort"
