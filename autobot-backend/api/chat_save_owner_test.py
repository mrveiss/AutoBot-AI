# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path that creates a session file must write the durable owner (#14020).

`save_chat_by_id` called `save_session` with no `metadata`, and
`_build_session_chat_data` writes the key only `if metadata:`. So a session
created through the save endpoint — rather than `POST /chat/sessions` — had no
`metadata.owner`.

Since #14018 made the file record authoritative, that is not cosmetic: such a
session reads as *genuinely unowned* every time its 24-hour Redis key lapses, and
is claimed by whoever visits next. Permanently reclaimable, once per TTL window.

The invariant these tests pin: a session with no durable owner gets one; a
session that already has one never has it overwritten by whoever is saving.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api import chat as chat_api

_ALICE = {"username": "alice", "user_id": "alice-id"}


def _manager(existing_owner):
    manager = MagicMock()
    manager.get_session_owner = AsyncMock(return_value=existing_owner)
    return manager


class TestANewSessionGetsADurableOwner:
    @pytest.mark.asyncio
    async def test_an_unowned_session_is_given_the_savers_owner_metadata(self):
        metadata = await chat_api._durable_owner_metadata(_manager(None), "chat-new", _ALICE)

        assert metadata == {"owner": "alice", "username": "alice"}

    @pytest.mark.asyncio
    async def test_both_keys_are_written(self):
        """`create_session` writes both, and the shared owner lookup falls back to
        `username` for sessions predating the `owner` field. Writing only one
        would make this path's sessions look different from every other."""
        metadata = await chat_api._durable_owner_metadata(_manager(None), "chat-new", _ALICE)

        assert set(metadata) == {"owner", "username"}


class TestAnExistingOwnerIsNeverOverwritten:
    @pytest.mark.asyncio
    async def test_a_session_that_already_has_an_owner_is_left_alone(self):
        """Returning metadata here would let any saver rewrite the durable record."""
        metadata = await chat_api._durable_owner_metadata(_manager("alice"), "chat-1", {"username": "bob"})

        assert metadata is None

    @pytest.mark.asyncio
    async def test_an_owner_lookup_failure_writes_nothing(self):
        """Not being able to tell whether an owner exists is not a licence to claim."""
        manager = MagicMock()
        manager.get_session_owner = AsyncMock(side_effect=RuntimeError("storage down"))

        assert await chat_api._durable_owner_metadata(manager, "chat-1", _ALICE) is None

    @pytest.mark.asyncio
    async def test_an_anonymous_saver_writes_nothing(self):
        assert await chat_api._durable_owner_metadata(_manager(None), "chat-1", None) is None
        assert await chat_api._durable_owner_metadata(_manager(None), "chat-1", {}) is None
