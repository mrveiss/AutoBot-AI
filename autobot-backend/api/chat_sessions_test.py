# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for chat_sessions._clear_session_messages (Issue #7025, #14359).

Background: pre-fix, the helper called ``chat_manager.add_message(session_id, dict)``
— the same broken signature pattern that #6744 fixed in api/chat.py. Python
silently accepted UUID as ``sender`` and dict as ``text``, leaving session_id
defaulted to None so the message landed in the in-memory default bucket
instead of the session's disk file. Restored system messages on reset_chat
were never persisted.

#14359: the restore path this helper supported (``keep_system_prompt`` /
``_preserve_system_messages`` / ``_to_persisted_system_message``) is removed —
nothing ever persists a system prompt into a session, so there was never
anything to restore. The helper (renamed from ``_clear_and_restore_session``
to ``_clear_session_messages``) now only clears.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.chat_sessions import _clear_session_messages


class TestClearSessionMessages:
    """Issue #7025 / #14359: the helper clears via update_session and nothing else."""

    @pytest.mark.asyncio
    async def test_clears_the_session_via_update_session(self):
        chat_manager = MagicMock(spec=["update_session"])
        chat_manager.update_session = AsyncMock(return_value=True)

        await _clear_session_messages(chat_manager, "session-X")

        chat_manager.update_session.assert_awaited_once_with("session-X", {"messages": []})

    @pytest.mark.asyncio
    async def test_does_not_touch_add_messages_batch(self):
        """No restore path remains: a manager that would raise on
        add_messages_batch must never see it called."""
        chat_manager = MagicMock(spec=["update_session", "add_messages_batch"])
        chat_manager.update_session = AsyncMock(return_value=True)
        chat_manager.add_messages_batch = AsyncMock(side_effect=AssertionError("must not restore anything"))

        await _clear_session_messages(chat_manager, "session-Y")

        chat_manager.add_messages_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_works_against_a_manager_without_add_messages_batch(self):
        """A legacy manager exposing only update_session is sufficient now that
        there is no restore step requiring add_messages_batch."""

        class _Legacy:
            async def update_session(self, sid, updates):
                self.cleared = (sid, updates)
                return True

        legacy = _Legacy()

        await _clear_session_messages(legacy, "session-Z")

        assert legacy.cleared == ("session-Z", {"messages": []})
