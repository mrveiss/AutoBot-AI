# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A failing cache comparison never discards the durable history projection (#21847)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chat_workflow.conversation import ConversationHandlerMixin

HISTORY = [{"user": "hi", "assistant": "hello"}]


def _handler(cached) -> ConversationHandlerMixin:
    handler = ConversationHandlerMixin.__new__(ConversationHandlerMixin)
    handler.redis_client = MagicMock()
    handler._project_from_chat_sessions = AsyncMock(return_value=HISTORY)
    handler._try_redis_history = (
        AsyncMock(side_effect=cached) if isinstance(cached, Exception) else AsyncMock(return_value=cached)
    )
    handler._save_conversation_history = AsyncMock()
    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [ConnectionError("redis down"), ValueError("invalid cached json")])
async def test_a_cache_failure_returns_the_projection(failure):
    assert await _handler(failure)._load_conversation_history("s1") == HISTORY


@pytest.mark.asyncio
async def test_an_unequal_cache_is_refilled_and_an_equal_one_is_left():
    with patch("chat_workflow.conversation.fire_and_forget") as fire:
        assert await _handler([])._load_conversation_history("s1") == HISTORY
        assert fire.call_count == 1
        fire.reset_mock()
        assert await _handler(HISTORY)._load_conversation_history("s1") == HISTORY
        assert fire.call_count == 0
