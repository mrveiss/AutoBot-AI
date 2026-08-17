# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What POST /chat/reset actually does, now that `keep_system_prompt` is gone (#14359).

`keep_system_prompt` guarded a restore step (`_preserve_system_messages` →
`_to_persisted_system_message` → the restore branch of what was
`_clear_and_restore_session`) that fed on state nothing ever wrote: a system
prompt is composed per turn by `ChatWorkflowManager._get_system_prompt()` and
sent straight to the provider, never persisted into a session. The only
production writers using the "system" speaker in a stored session are
operational notices (command approval/cancellation — see
`services/agent_terminal/approval_handler.py`,
`services/agent_terminal/command_executor.py`) and overflow summaries, neither
of which is a system prompt.

So flipping the flag could never change what a reset actually did — the two
branches it selected between (`_preserve_system_messages(...)` vs `[]`)
produced the same empty result on every real session, which #14306 and
#14359's own test suite already pinned before this change. The flag carried
no observable behaviour to remove; only the API surface pretending it did.

These tests drive `reset_chat` — the real endpoint function, not the removed
helpers directly — and assert the single unconditional behaviour that
replaces both former branches: a reset always clears, and nothing is ever
silently carried over.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import chat_sessions
from api.schemas_chat import ChatResetData, ChatResetRequest


def _manager():
    manager = MagicMock(spec=["update_session", "add_messages_batch"])
    manager.update_session = AsyncMock(return_value=True)
    manager.add_messages_batch = AsyncMock(return_value=None)
    return manager


@pytest.mark.asyncio
class TestResetAlwaysClearsNothingCarriedOver:
    """AC: 'a reset clears the session and that nothing is silently carried over.'"""

    async def test_a_reset_clears_the_session(self):
        manager = _manager()
        request = MagicMock()
        reset = ChatResetRequest(session_id="s-1", clear_context=True)

        with patch.object(chat_sessions, "validate_session_ownership", AsyncMock(return_value={})):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock(return_value=manager)):
                await chat_sessions.reset_chat(request, reset)

        manager.update_session.assert_awaited_once_with("s-1", {"messages": []})

    async def test_nothing_is_ever_restored(self):
        """The removed restore path must have no successor: add_messages_batch
        is never called by a reset, regardless of what the session held."""
        manager = _manager()
        request = MagicMock()
        reset = ChatResetRequest(session_id="s-1", clear_context=True)

        with patch.object(chat_sessions, "validate_session_ownership", AsyncMock(return_value={})):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock(return_value=manager)):
                await chat_sessions.reset_chat(request, reset)

        manager.add_messages_batch.assert_not_awaited()

    async def test_clear_context_false_does_not_touch_the_session(self):
        manager = _manager()
        request = MagicMock()
        reset = ChatResetRequest(session_id="s-1", clear_context=False)

        with patch.object(chat_sessions, "validate_session_ownership", AsyncMock(return_value={})):
            with patch.object(chat_sessions, "get_chat_history_manager", MagicMock(return_value=manager)):
                await chat_sessions.reset_chat(request, reset)

        manager.update_session.assert_not_awaited()


class TestTheFlagIsGoneFromTheContract:
    """AC: `keep_system_prompt` removed from the request/response schema."""

    def test_request_schema_has_no_keep_system_prompt_field(self):
        assert "keep_system_prompt" not in ChatResetRequest.model_fields

    def test_response_schema_has_no_keep_system_prompt_field(self):
        assert "keep_system_prompt" not in ChatResetData.model_fields

    def test_removed_helpers_are_gone_not_just_unused(self):
        """`_preserve_system_messages` and `_to_persisted_system_message` are
        removed outright, not merely dead code left importable."""
        assert not hasattr(chat_sessions, "_preserve_system_messages")
        assert not hasattr(chat_sessions, "_to_persisted_system_message")
        assert not hasattr(chat_sessions, "_clear_and_restore_session")
