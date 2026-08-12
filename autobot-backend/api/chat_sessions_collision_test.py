# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Creating over an existing session id must not destroy or take it over (#14012).

`create_session` accepts a caller-supplied id (#6746) and checked only its
**format**. Neither downstream step guarded a collision:

- `chat_history_manager.create_session` calls `save_session(..., messages=[])`,
  replacing the stored conversation with an empty list
- `set_session_owner` did an unconditional `redis.set`, with no existing-owner
  guard

So one request naming a victim's session id both destroyed their conversation
and made the attacker its registered owner — after which every *other* endpoint's
ownership check passes for them, because the record those checks consult now
says they are the owner.

Two layers are tested here, because either alone leaves the other reachable: the
endpoint refuses the collision, and the ownership record refuses a silent
reassignment regardless of who calls it.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import chat_sessions
from api.schemas_chat import SessionCreate

_ALICE = {"username": "alice", "user_id": "alice-id"}
_MALLORY = {"username": "mallory", "user_id": "mallory-id"}


def _manager(existing):
    manager = MagicMock()
    manager.get_session = AsyncMock(return_value=existing)
    manager.create_session = AsyncMock(return_value={"session_id": "chat-1"})
    return manager


def _session_owned_by(owner: str) -> dict:
    return {"session_id": "chat-1", "messages": [{"role": "user", "content": "secret"}], "metadata": {"owner": owner}}


class TestTheEndpointRefusesACollision:
    @pytest.mark.asyncio
    async def test_creating_over_another_users_session_is_refused(self):
        manager = _manager(_session_owned_by("alice"))

        with pytest.raises(HTTPException):
            await chat_sessions._reject_session_id_collision(manager, "chat-1", _MALLORY)

    @pytest.mark.asyncio
    async def test_a_free_id_is_allowed(self):
        """The common path — #6746's client-minted id for a genuinely new session."""
        manager = _manager(None)

        await chat_sessions._reject_session_id_collision(manager, "chat-new", _ALICE)

    @pytest.mark.asyncio
    async def test_the_owner_may_recreate_their_own_id(self):
        """A client retry, which the #6746 round-trip depends on."""
        manager = _manager(_session_owned_by("alice"))

        await chat_sessions._reject_session_id_collision(manager, "chat-1", _ALICE)

    @pytest.mark.asyncio
    async def test_an_existing_session_with_no_recorded_owner_is_refused(self):
        """Legacy sessions have no owner metadata. Unknown is not the same as free."""
        manager = _manager({"session_id": "chat-1", "messages": [{"role": "user", "content": "x"}], "metadata": {}})

        with pytest.raises(HTTPException):
            await chat_sessions._reject_session_id_collision(manager, "chat-1", _MALLORY)

    @pytest.mark.asyncio
    async def test_an_anonymous_caller_cannot_claim_an_owned_session(self):
        manager = _manager(_session_owned_by("alice"))

        with pytest.raises(HTTPException):
            await chat_sessions._reject_session_id_collision(manager, "chat-1", None)

    @pytest.mark.asyncio
    async def test_a_lookup_failure_refuses_rather_than_overwrites(self):
        """Not being able to tell whether a session exists is not a reason to overwrite it."""
        manager = MagicMock()
        manager.get_session = AsyncMock(side_effect=RuntimeError("storage down"))

        with pytest.raises(HTTPException):
            await chat_sessions._reject_session_id_collision(manager, "chat-1", _ALICE)


class TestTheEndpointActuallyCallsTheGuard:
    """The guard being correct is not the same as the endpoint using it.

    Testing `_reject_session_id_collision` directly cannot see the call site —
    deleting the call from `create_session` left every helper test green. This
    drives the endpoint so the wiring itself is pinned.
    """

    @pytest.mark.asyncio
    async def test_create_over_another_users_session_is_refused_end_to_end(self, monkeypatch):
        manager = _manager(_session_owned_by("alice"))
        middleware = MagicMock()
        middleware.get_user_from_request.return_value = _MALLORY

        monkeypatch.setattr(chat_sessions, "get_chat_history_manager", MagicMock(return_value=manager))
        monkeypatch.setattr(chat_sessions, "get_auth_middleware", MagicMock(return_value=middleware))
        monkeypatch.setattr(chat_sessions, "validate_chat_session_id", MagicMock(return_value=True))

        with pytest.raises(HTTPException) as excinfo:
            await chat_sessions.create_session(SessionCreate(id="chat-1", title="mine now"), MagicMock())

        assert excinfo.value.status_code == 409, "must not surface as a generic 500"

        manager.create_session.assert_not_called(), "nothing may be written on a refused create"


class TestTheOwnershipRecordRefusesAReassignment:
    """Defence in depth: a future caller that skips the endpoint check still cannot take over."""

    @staticmethod
    def _validator(existing_owner):
        from security.session_ownership import SessionOwnershipValidator

        validator = SessionOwnershipValidator.__new__(SessionOwnershipValidator)
        validator.redis = MagicMock()
        validator.redis.set = AsyncMock()
        validator.redis.sadd = AsyncMock()
        validator.redis.expire = AsyncMock()
        validator.ownership_ttl = 3600
        validator.get_session_owner = AsyncMock(return_value=existing_owner)
        return validator

    @pytest.mark.asyncio
    async def test_a_different_owner_is_not_silently_overwritten(self):
        validator = self._validator("alice")

        result = await validator.set_session_owner(session_id="chat-1", username="mallory")

        assert result is False
        validator.redis.set.assert_not_awaited(), "the ownership key must not be rewritten"

    @pytest.mark.asyncio
    async def test_an_unowned_session_can_be_claimed(self):
        """First registration — what create_session legitimately does."""
        validator = self._validator(None)

        assert await validator.set_session_owner(session_id="chat-1", username="alice") is True
        validator.redis.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_the_owner_may_refresh_their_own_record(self):
        """The TTL refresh path must keep working, or ownership expires under active use."""
        validator = self._validator("alice")

        assert await validator.set_session_owner(session_id="chat-1", username="alice") is True
        validator.redis.set.assert_awaited()

    @pytest.mark.asyncio
    async def test_a_deliberate_transfer_must_say_so(self):
        validator = self._validator("alice")

        assert await validator.set_session_owner(session_id="chat-1", username="bob", force=True) is True
        validator.redis.set.assert_awaited()
