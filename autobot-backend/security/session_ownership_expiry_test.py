# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An expired ownership record must not hand the session to the next caller (#14018).

Ownership was recorded in two independent places:

- the session file's ``metadata.owner`` — permanent
- the Redis ownership key — ``ownership_ttl = 86400`` (24 hours)

Every ownership check consults the Redis one. ``_resolve_ownership`` treated
"no stored owner" as a legacy session and **claimed it for the caller**, returning
``authorized: True``. But "no stored owner" is not only the legacy case — it is
also every session whose TTL has lapsed. So a session its owner had not touched
for a day was handed to whoever accessed it next, with the file still naming the
real owner and nothing reading it.

The fix asks the durable record before claiming. These tests pin the distinction
that makes it work: *never recorded* is claimable, *expired* is not.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from security.session_ownership import SessionOwnershipValidator

_ALICE = "alice"
_BOB = "bob"


def _validator(*, redis_owner, file_owner):
    """A validator whose Redis cache and durable file record can disagree."""
    validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
    validator.redis = MagicMock()
    validator.ownership_ttl = 86400
    validator.get_session_owner = AsyncMock(return_value=redis_owner)
    validator.set_session_owner = AsyncMock(return_value=True)
    validator._durable_owner = AsyncMock(return_value=file_owner)
    validator._check_ownership_mismatch = AsyncMock(
        return_value={"authorized": False, "user_data": {}, "reason": "mismatch"}
    )
    validator._audit_log_success = MagicMock()
    return validator


async def _resolve(validator, username):
    return await validator._resolve_ownership(
        session_id="chat-1",
        username=username,
        user_data={"username": username},
        request=MagicMock(),
        enforcement_mode="enforced",
    )


class TestAnExpiredRecordIsNotAnUnownedSession:
    @pytest.mark.asyncio
    async def test_a_stranger_cannot_claim_a_session_whose_cache_expired(self):
        """The defect, in one assertion.

        Alice owns the session on disk. Her Redis key has lapsed. Bob arrives.
        """
        validator = _validator(redis_owner=None, file_owner=_ALICE)

        result = await _resolve(validator, _BOB)

        assert result["reason"] != "legacy_migration", "an expired record must not read as unowned"
        assert result["authorized"] is False
        validator._check_ownership_mismatch.assert_awaited(), "must go through the mismatch path"

    @pytest.mark.asyncio
    async def test_the_cache_is_never_rehydrated_for_the_wrong_user(self):
        """Claiming for the caller is what converted expiry into a takeover."""
        validator = _validator(redis_owner=None, file_owner=_ALICE)

        await _resolve(validator, _BOB)

        validator.set_session_owner.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_real_owner_still_gets_in_after_expiry(self):
        """The other half — the fix must not lock the owner out of their own session."""
        validator = _validator(redis_owner=None, file_owner=_ALICE)

        result = await _resolve(validator, _ALICE)

        assert result["authorized"] is True
        assert result["reason"] == "owner_match"

    @pytest.mark.asyncio
    async def test_the_owners_access_rehydrates_the_cache(self):
        """Otherwise every request after expiry pays the file read."""
        validator = _validator(redis_owner=None, file_owner=_ALICE)

        await _resolve(validator, _ALICE)

        validator.set_session_owner.assert_awaited_once()
        assert validator.set_session_owner.await_args.args[1] == _ALICE


class TestAGenuinelyUnownedSessionIsStillClaimable:
    """The real legacy case must keep working, or old sessions become unreachable."""

    @pytest.mark.asyncio
    async def test_no_owner_anywhere_is_claimed_by_the_caller(self):
        validator = _validator(redis_owner=None, file_owner=None)

        result = await _resolve(validator, _BOB)

        assert result["authorized"] is True
        assert result["reason"] == "legacy_migration"
        validator.set_session_owner.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_an_unreadable_session_is_treated_as_unowned_not_as_a_denial(self):
        """`_durable_owner` returns None on a read failure; that path is the legacy one."""
        validator = _validator(redis_owner=None, file_owner=None)

        result = await _resolve(validator, _ALICE)

        assert result["reason"] == "legacy_migration"


class TestThePresentCacheStillDecides:
    """When Redis has a record, the durable read must not run at all."""

    @pytest.mark.asyncio
    async def test_the_owner_is_authorized_without_touching_the_file(self):
        validator = _validator(redis_owner=_ALICE, file_owner=_ALICE)

        result = await _resolve(validator, _ALICE)

        assert result["reason"] == "owner_match"
        validator._durable_owner.assert_not_awaited(), "the cache hit must not pay a file read"

    @pytest.mark.asyncio
    async def test_a_mismatch_still_goes_to_the_mismatch_path(self):
        validator = _validator(redis_owner=_ALICE, file_owner=_ALICE)

        result = await _resolve(validator, _BOB)

        assert result["authorized"] is False
        validator._durable_owner.assert_not_awaited()


class TestTheDurableLookupSeesOlderSessions:
    """The owner field is not the only durable record (#14019 review).

    Sessions predating the `owner` field carry `metadata.username` instead, and
    `create_session` still writes both keys for exactly that reason. Parsing only
    `owner` read those as unowned and handed them to their next visitor — this
    issue's own defect, reintroduced for that vintage of file.

    `ChatHistoryManager.get_session_owner` already resolves
    `owner or username`, so `_durable_owner` delegates to it rather than
    reimplementing the parse.
    """

    @staticmethod
    def _validator_with_manager(manager):
        validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
        validator.redis = MagicMock()
        validator.ownership_ttl = 86400
        return validator

    @pytest.mark.asyncio
    async def test_a_username_only_session_is_recognised_as_owned(self, monkeypatch):
        manager = MagicMock()
        # What the shared accessor returns for a pre-`owner` session file.
        manager.get_session_owner = AsyncMock(return_value=_ALICE)
        monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", MagicMock(return_value=manager))

        validator = self._validator_with_manager(manager)
        owner = await validator._durable_owner("chat-1", MagicMock())

        assert owner == _ALICE, "an older session must not read as unowned"

    @pytest.mark.asyncio
    async def test_the_shared_accessor_is_used_not_a_local_reparse(self, monkeypatch):
        """Pins the delegation: a reimplementation here would miss the fallback."""
        manager = MagicMock()
        manager.get_session_owner = AsyncMock(return_value=_ALICE)
        monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", MagicMock(return_value=manager))

        validator = self._validator_with_manager(manager)
        await validator._durable_owner("chat-1", MagicMock())

        manager.get_session_owner.assert_awaited_once_with("chat-1")

    @pytest.mark.asyncio
    async def test_a_session_with_no_durable_owner_yields_none(self, monkeypatch):
        manager = MagicMock()
        manager.get_session_owner = AsyncMock(return_value=None)
        monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", MagicMock(return_value=manager))

        validator = self._validator_with_manager(manager)

        assert await validator._durable_owner("chat-1", MagicMock()) is None

    @pytest.mark.asyncio
    async def test_a_read_failure_yields_none_and_is_logged(self, monkeypatch, caplog):
        manager = MagicMock()
        manager.get_session_owner = AsyncMock(side_effect=RuntimeError("storage down"))
        monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", MagicMock(return_value=manager))

        validator = self._validator_with_manager(manager)
        with caplog.at_level("WARNING"):
            result = await validator._durable_owner("chat-1", MagicMock())

        assert result is None
        assert any("durable owner" in r.message for r in caplog.records), "the fail-open must not be silent"
