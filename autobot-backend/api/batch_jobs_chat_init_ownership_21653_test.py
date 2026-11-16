# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every chat-session list route returns only the caller's own sessions (#21653, #21664).

``/api/batch-jobs/chat-init`` used to walk every ``chat_*.json`` in the chats directory, and
``GET /api/chats`` (alias ``/api/chat/chats``) returned ``list_sessions_fast()`` unfiltered, so
any signed-in user could read every other user's session ids. Both now call
``api.chat_sessions.list_user_sessions`` -- the listing behind ``GET /api/chat/sessions`` -- so
all three routes apply the one ownership filter (``_filter_user_sessions`` over
``security.session_owner_index.owned_session_ids``).

Administrators get no bypass, matching the canonical route's default scope.

All routes fail closed (#21664, decided 2026-11-16): a caller who owns nothing, or a principal
with no username, gets ``[]`` -- never the instance-wide list. An owner index that has expired
from Redis is rebuilt from the session files' durable owner, so an owner still sees their own.

The ownership store is doubled the way ``tests/test_chat_session_ownership_failclosed.py``
doubles it: ``_build_ownership_validator`` patched to a validator with a per-user map.
"""

import ast
import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.batch_jobs as batch_jobs
import api.chat as chat
import api.chat_sessions as chat_sessions
from api.chat_sessions_errors import OwnershipUnavailableError

_SESSIONS = [
    {"id": "alice-1", "title": "Alice's chat"},
    {"id": "bob-1", "title": "Bob's chat"},
    {"id": "root-1", "title": "Admin's chat"},
]
_DISK = {"alice-1": "alice", "bob-1": "bob", "root-1": "root"}  # metadata.owner in each session file
_INDEX = {"alice": ["alice-1"], "bob": ["bob-1"], "root": ["root-1"]}  # the Redis owner index

ALICE = {"username": "alice", "role": "user"}
BOB = {"username": "bob", "role": "user"}
ADMIN = {"username": "root", "role": "admin"}
NEWCOMER = {"username": "carol", "role": "user"}  # signed in, owns no session yet
NAMELESS = {"role": "service"}  # authenticated principal with no username


def _validator(index=None, error=None):
    """``index=None``: the cached index, marked complete. ``index={}``: expired, no marker (#21664)."""
    marked, index = index is None, _INDEX if index is None else index
    v = MagicMock()
    v.get_user_sessions = AsyncMock(side_effect=error or (lambda username: index.get(username, [])))
    v.set_session_owner = AsyncMock(return_value=True)
    v.redis.exists = AsyncMock(return_value=int(marked))
    v.redis.set = AsyncMock(return_value=True)
    return v


def _manager():
    manager = MagicMock()
    manager.list_sessions_fast = AsyncMock(return_value=[dict(s) for s in _SESSIONS])
    manager.get_session_owner = AsyncMock(side_effect=lambda sid: _DISK.get(sid))
    return manager


def _app(manager):
    return SimpleNamespace(state=SimpleNamespace(chat_history_manager=manager))


def _ids(sessions) -> list[str]:
    return sorted(s["id"] for s in sessions)


def _payload_sessions(response):
    payload = json.loads(response.body) if hasattr(response, "body") else response
    data = payload.get("data", payload)
    return data["sessions"] if isinstance(data, dict) else data


async def _chat_init(user, manager, validator):
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch.object(chat_sessions, "_build_ownership_validator", return_value=validator):
            request = SimpleNamespace(app=_app(manager))
            response = await batch_jobs.batch_chat_initialization(request, current_user=user)
    return _ids(response["chat_sessions"]["sessions"])


async def _chat_sessions_route(user, manager, validator):
    """``GET /api/chat/sessions`` default scope, called the way the tenancy-scope test calls it."""
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch.object(chat_sessions, "get_chat_history_manager", return_value=manager):
            with patch.object(chat_sessions, "_build_ownership_validator", return_value=validator):
                response = await chat_sessions.list_sessions(MagicMock(), user, scope=None, team_id=None)
    return _ids(_payload_sessions(response))


async def _chats_route(user, manager, validator):
    """``GET /api/chats`` and its ``/api/chat/chats`` alias (one handler, ``list_chats``)."""
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch.object(chat_sessions, "_build_ownership_validator", return_value=validator):
            response = await chat.list_chats(current_user=user, request=SimpleNamespace(app=_app(manager)))
    return _ids(_payload_sessions(response))


_ROUTES = pytest.mark.parametrize(
    "route", [_chat_init, _chat_sessions_route, _chats_route], ids=["chat-init", "sessions", "chats"]
)


@_ROUTES
@pytest.mark.asyncio
async def test_another_users_session_is_absent(route):
    assert "alice-1" not in await route(BOB, _manager(), _validator())


@_ROUTES
@pytest.mark.asyncio
async def test_a_caller_with_records_sees_only_their_own(route):
    assert await route(ALICE, _manager(), _validator()) == ["alice-1"]


@_ROUTES
@pytest.mark.asyncio
async def test_an_admin_lists_only_their_own_sessions(route):
    """No role bypass -- the same as the default scope of ``GET /api/chat/sessions``."""
    assert await route(ADMIN, _manager(), _validator()) == ["root-1"]


@_ROUTES
@pytest.mark.asyncio
async def test_a_caller_with_no_ownership_records_gets_nothing(route):
    assert await route(NEWCOMER, _manager(), _validator()) == []


@_ROUTES
@pytest.mark.asyncio
async def test_a_principal_with_no_username_gets_nothing(route):
    manager = _manager()
    assert await route(NAMELESS, manager, _validator()) == []
    manager.list_sessions_fast.assert_not_awaited()


@_ROUTES
@pytest.mark.asyncio
async def test_an_expired_owner_index_is_rebuilt_from_the_session_files(route):
    """Redis set gone (30-day TTL); the file's metadata.owner still names alice (THREAT_MODEL s.2)."""
    validator = _validator(index={})
    assert await route(ALICE, _manager(), validator) == ["alice-1"]
    validator.set_session_owner.assert_awaited_once_with("alice-1", "alice")


@pytest.mark.asyncio
async def test_chat_init_returns_no_sessions_when_the_ownership_store_is_down():
    validator = _validator(error=ConnectionError("redis down"))
    assert await _chat_init(ALICE, _manager(), validator) == []


@pytest.mark.parametrize("route", [_chat_sessions_route, _chats_route], ids=["sessions", "chats"])
@pytest.mark.asyncio
async def test_a_store_outage_is_a_503_not_an_intentional_empty_list(route):
    """A Redis blip must not answer ``intentional_empty`` -- that tells the UI to wipe its sessions."""
    with pytest.raises(OwnershipUnavailableError) as exc:
        await route(ALICE, _manager(), _validator(error=ConnectionError("redis down")))
    assert exc.value.status_code == 503


def _calls(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn).lstrip())
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def test_every_list_route_shares_one_listing():
    """One ownership mechanism: each chat-session list route calls the same helper."""
    for fn in (batch_jobs.get_chat_sessions, chat_sessions.list_sessions, chat.list_chats):
        assert "list_user_sessions" in _calls(fn), fn.__name__
