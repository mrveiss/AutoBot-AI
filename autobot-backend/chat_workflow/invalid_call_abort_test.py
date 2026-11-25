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
