# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``scope=team`` lists a team's sessions only to its members and to administrators (#21667)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from api import chat_session_team_access as access
from api import chat_sessions

_TEAM = str(uuid.uuid4())
_USER = {"username": "alice", "role": "user", "user_id": str(uuid.uuid4())}
_ADMIN = {"username": "root", "role": "admin"}


@pytest.fixture
def membership(monkeypatch):
    """The canonical TeamService answer, in place of a database."""
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(access, "_is_member", check)
    return check


@pytest.mark.asyncio
async def test_a_member_passes(membership) -> None:
    await access.require_team_member(_USER, _TEAM)

    membership.assert_awaited_once_with(_USER, _TEAM)


@pytest.mark.asyncio
async def test_a_non_member_is_refused(membership) -> None:
    membership.return_value = False

    with pytest.raises(HTTPException) as refused:
        await access.require_team_member(_USER, _TEAM)

    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_an_administrator_passes_without_a_membership_lookup(membership) -> None:
    await access.require_team_member(_ADMIN, _TEAM)

    membership.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("db down"), ValueError("malformed id")])
async def test_an_undecidable_membership_refuses(membership, failure) -> None:
    membership.side_effect = failure

    with pytest.raises(HTTPException) as refused:
        await access.require_team_member(_USER, _TEAM)

    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_a_user_with_no_user_id_is_refused() -> None:
    with pytest.raises(HTTPException):
        await access.require_team_member({"username": "alice", "role": "user"}, _TEAM)


@pytest.mark.asyncio
@pytest.mark.parametrize("member, listed", [(False, False), (True, True)])
async def test_team_scope_lists_only_after_the_membership_check(monkeypatch, membership, member, listed) -> None:
    membership.return_value = member
    auth = MagicMock()
    auth.get_user_from_request.return_value = _USER
    monkeypatch.setattr(chat_sessions, "get_auth_middleware", lambda: auth)
    monkeypatch.setattr("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=MagicMock()))
    team_list = AsyncMock(return_value="team-sessions")
    monkeypatch.setattr(chat_sessions, "_list_team_sessions", team_list)

    async def _call():
        return await chat_sessions._list_scoped_sessions(MagicMock(), "r1", MagicMock(), "team", _TEAM)

    if listed:
        assert await _call() == "team-sessions"
    else:
        with pytest.raises(HTTPException):
            await _call()
    assert team_list.await_count == int(listed)
