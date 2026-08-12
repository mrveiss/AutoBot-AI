# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path that creates a session file must write the durable owner (#14020).

`save_chat_by_id` called `save_session` with no `metadata`, and
`_build_session_chat_data` writes the key only `if metadata:`. So a session
created through the save endpoint — rather than `POST /chat/sessions` — had no
`metadata.owner`.

Since #14018 made the file record authoritative that is not cosmetic: such a
session reads as *genuinely unowned* every time its 24-hour Redis key lapses, and
is claimed by whoever visits next.

The write **mirrors the validator's decision** instead of making its own. That
distinction is the whole safety argument, and the tests that matter most are the
ones pinning when it must NOT write: the `enforcement_disabled` and
`auth_disabled` fast paths authorise without checking any owner, so claiming
there would let any authenticated caller stamp themselves onto an ownerless
session — permanently, outliving the eventual switch to enforced.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import chat as chat_api

_ALICE = {"username": "alice", "user_id": "alice-id", "org_id": "org-1"}


def _ownership(reason, user_data=None):
    return {"authorized": True, "user_data": user_data if user_data is not None else _ALICE, "reason": reason}


class TestItWritesOnlyWhenTheValidatorJustClaimed:
    @pytest.mark.asyncio
    async def test_a_legacy_migration_stamps_the_owner(self):
        """The validator found no owner and granted it — record what happened."""
        metadata = await chat_api._durable_owner_metadata(MagicMock(), "chat-new", _ownership("legacy_migration"))

        assert metadata["owner"] == "alice"
        assert metadata["username"] == "alice"

    @pytest.mark.asyncio
    async def test_the_org_hierarchy_is_carried_too(self):
        """Shared with create_session, so the two paths cannot drift (#684)."""
        metadata = await chat_api._durable_owner_metadata(MagicMock(), "chat-new", _ownership("legacy_migration"))

        assert metadata["user_id"] == "alice-id"
        assert metadata["org_id"] == "org-1"

    @pytest.mark.asyncio
    async def test_an_owner_match_writes_nothing(self):
        """The session already has an owner; nothing to record."""
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("owner_match")) is None


class TestItNeverClaimsOnAnUncheckedFastPath:
    """The finding that made the first version of this fix harmful.

    `enforcement_disabled` is the DEFAULT today (#14010): `_resolve_fast_paths`
    returns authorized without consulting any owner. Writing an owner there is a
    land grab, not a record.
    """

    @pytest.mark.asyncio
    async def test_enforcement_disabled_writes_nothing(self):
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("enforcement_disabled")) is None

    @pytest.mark.asyncio
    async def test_auth_disabled_writes_nothing(self):
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("auth_disabled")) is None

    @pytest.mark.asyncio
    async def test_log_only_mode_writes_nothing(self):
        """log_only reports what enforcement *would* do; it decides nothing."""
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("log_only_mode")) is None

    @pytest.mark.asyncio
    async def test_org_admin_and_shared_access_write_nothing(self):
        """Both authorise someone who is explicitly NOT the owner."""
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("org_admin")) is None
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("shared_access")) is None

    @pytest.mark.asyncio
    async def test_a_missing_or_malformed_ownership_result_writes_nothing(self):
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", None) is None
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", {}) is None
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", "not-a-dict") is None

    @pytest.mark.asyncio
    async def test_a_claim_with_no_username_writes_nothing(self):
        assert await chat_api._durable_owner_metadata(MagicMock(), "chat-1", _ownership("legacy_migration", {})) is None


class TestTheEndpointActuallyPassesIt:
    """Testing the helper is not testing that anything uses it.

    A previous PR in this series had exactly this mutant survive, and the
    existing endpoint test only asserts `save_session.called`, never its kwargs.
    """

    @staticmethod
    async def _save(ownership):
        manager = MagicMock()
        manager.save_session = AsyncMock(return_value={"session_id": "chat-1"})
        with patch.object(chat_api, "get_chat_history_manager", MagicMock(return_value=manager)):
            with patch.object(chat_api, "_merge_chat_messages", AsyncMock(return_value=[])):
                await chat_api.save_chat_by_id(
                    chat_id="chat-1",
                    current_user=_ALICE,
                    request_data={"data": {"messages": [], "name": "n"}},
                    request=MagicMock(),
                    ownership=ownership,
                )
        return manager.save_session.call_args.kwargs

    @pytest.mark.asyncio
    async def test_the_owner_metadata_reaches_save_session(self):
        kwargs = await self._save(_ownership("legacy_migration"))

        assert kwargs["metadata"]["owner"] == "alice"

    @pytest.mark.asyncio
    async def test_nothing_is_written_on_an_unchecked_fast_path(self):
        kwargs = await self._save(_ownership("enforcement_disabled"))

        assert kwargs["metadata"] is None, "must not stamp an owner the validator never verified"
