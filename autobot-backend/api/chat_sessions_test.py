# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for chat_sessions._clear_and_restore_session (Issue #7025).

Background: pre-fix, the helper called ``chat_manager.add_message(session_id, dict)``
— the same broken signature pattern that #6744 fixed in api/chat.py. Python
silently accepted UUID as ``sender`` and dict as ``text``, leaving session_id
defaulted to None so the message landed in the in-memory default bucket
instead of the session's disk file. Restored system messages on reset_chat
were never persisted.

Tests below pin the contract: ``_clear_and_restore_session`` uses
``add_messages_batch`` with the disk-shape schema, and is properly awaited.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.chat_sessions import (
    _clear_and_restore_session,
    _to_persisted_system_message,
)


class TestToPersistedSystemMessage:
    """Issue #7025: api-shape (role/content) → disk-shape (sender/content/type)."""

    def test_translates_role_to_sender(self):
        result = _to_persisted_system_message({"id": "m1", "role": "system", "content": "You are a helper."})
        assert result["sender"] == "system"
        assert result["content"] == "You are a helper."
        assert result["id"] == "m1"

    def test_existing_sender_field_takes_priority_when_role_absent(self):
        result = _to_persisted_system_message({"id": "m2", "sender": "system", "content": "x"})
        assert result["sender"] == "system"

    def test_falls_back_to_system_when_neither_role_nor_sender(self):
        result = _to_persisted_system_message({"id": "m3", "content": "x"})
        assert result["sender"] == "system"

    def test_default_metadata_and_sources(self):
        result = _to_persisted_system_message({"id": "m4", "role": "system", "content": "x"})
        assert result["metadata"] == {}
        assert result["sources"] == []
        assert result["type"] == "message"


class TestClearAndRestoreSession:
    """Issue #7025: async helper uses add_messages_batch (not broken add_message)."""

    @pytest.mark.asyncio
    async def test_calls_add_messages_batch_with_persisted_shape(self):
        """The helper must translate role→sender and call add_messages_batch."""
        chat_manager = MagicMock()
        chat_manager.clear_session = MagicMock()
        chat_manager.add_messages_batch = AsyncMock(return_value=None)

        messages = [
            {"id": "s1", "role": "system", "content": "rule 1"},
            {"id": "s2", "role": "system", "content": "rule 2"},
        ]

        restored = await _clear_and_restore_session(chat_manager, "session-X", messages)

        assert restored == 2
        chat_manager.clear_session.assert_called_once_with("session-X")
        chat_manager.add_messages_batch.assert_awaited_once()

        call_args = chat_manager.add_messages_batch.await_args
        assert call_args.args[0] == "session-X"
        persisted = call_args.args[1]
        assert len(persisted) == 2
        assert persisted[0]["sender"] == "system"
        assert persisted[0]["content"] == "rule 1"
        assert persisted[1]["sender"] == "system"

    @pytest.mark.asyncio
    async def test_no_op_when_no_messages_to_restore(self):
        """Empty list must clear the session but not call add_messages_batch."""
        chat_manager = MagicMock()
        chat_manager.clear_session = MagicMock()
        chat_manager.add_messages_batch = AsyncMock(return_value=None)

        restored = await _clear_and_restore_session(chat_manager, "session-Y", [])

        assert restored == 0
        chat_manager.clear_session.assert_called_once_with("session-Y")
        chat_manager.add_messages_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_through_when_chat_manager_lacks_batch_method(self):
        """Older chat managers without add_messages_batch must not blow up."""

        class _Legacy:
            def clear_session(self, sid):
                self.cleared = sid

        legacy = _Legacy()
        # Note: pre-fix, this code called add_message which DOES exist on the
        # legacy manager but with the wrong shape. Now we just skip persistence
        # if add_messages_batch is unavailable. The test pins this behavior so
        # it is intentional, not accidental.
        restored = await _clear_and_restore_session(
            legacy, "session-Z", [{"id": "s1", "role": "system", "content": "x"}]
        )

        assert restored == 1  # we still report the count
        assert legacy.cleared == "session-Z"
