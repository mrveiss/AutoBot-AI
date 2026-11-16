# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/api/batch-jobs/chat-init`` lists only the caller's own chat sessions (#21653).

It used to walk every ``chat_*.json`` in the chats directory and return each id with no
owner filter, so any signed-in user could read every other user's session ids. It now
calls ``api.chat_sessions.list_user_sessions`` -- the listing behind ``GET /chat/sessions``
-- so both routes apply the one ownership filter (``_filter_user_sessions`` over
``SessionOwnershipValidator.get_user_sessions``).

Administrators get no bypass, matching the canonical route's default scope: an admin's
``/chat-init`` lists the admin's own sessions only.

Both routes fail closed (#21664, decided 2026-11-16): a caller with no ownership records, or
a principal with no username, gets ``[]`` -- never the instance-wide list.

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
import api.chat_sessions as chat_sessions

_SESSIONS = [
    {"id": "alice-1", "title": "Alice's chat"},
    {"id": "bob-1", "title": "Bob's chat"},
    {"id": "root-1", "title": "Admin's chat"},
]
_OWNED = {"alice": ["alice-1"], "bob": ["bob-1"], "root": ["root-1"]}

ALICE = {"username": "alice", "role": "user"}
BOB = {"username": "bob", "role": "user"}
ADMIN = {"username": "root", "role": "admin"}
NEWCOMER = {"username": "carol", "role": "user"}  # signed in, owns no session yet
NAMELESS = {"role": "service"}  # authenticated principal with no username


def _validator():
    v = MagicMock()
    v.get_user_sessions = AsyncMock(side_effect=lambda username: _OWNED.get(username, []))
    return v


def _manager():
    manager = MagicMock()
    manager.list_sessions_fast = AsyncMock(return_value=[dict(s) for s in _SESSIONS])
    return manager


def _request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(chat_history_manager=_manager())))


async def _chat_init_ids(user) -> list[str]:
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch("api.chat_sessions._build_ownership_validator", return_value=_validator()):
            response = await batch_jobs.batch_chat_initialization(_request(), current_user=user)
    return sorted(s["id"] for s in response["chat_sessions"]["sessions"])


@pytest.mark.asyncio
async def test_another_users_session_is_absent():
    assert "alice-1" not in await _chat_init_ids(BOB)


@pytest.mark.asyncio
async def test_the_callers_own_session_is_present():
    assert await _chat_init_ids(ALICE) == ["alice-1"]


@pytest.mark.asyncio
async def test_an_admin_lists_only_their_own_sessions():
    """No role bypass -- the same as the default scope of ``GET /chat/sessions``."""
    assert await _chat_init_ids(ADMIN) == ["root-1"]


@pytest.mark.asyncio
async def test_an_ownership_outage_returns_no_sessions_rather_than_all():
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock(side_effect=RuntimeError("down"))):
        response = await batch_jobs.batch_chat_initialization(_request(), current_user=ALICE)
    assert response["chat_sessions"] == {"sessions": []}


async def _chat_sessions_route_ids(user) -> list[str]:
    """``GET /api/chat/sessions`` default scope, called the way the tenancy-scope test calls it."""
    with patch("autobot_shared.redis_client.get_redis_client", new=AsyncMock()):
        with patch.object(chat_sessions, "get_chat_history_manager", return_value=_manager()):
            with patch.object(chat_sessions, "_build_ownership_validator", return_value=_validator()):
                response = await chat_sessions.list_sessions(MagicMock(), user, scope=None, team_id=None)
    payload = json.loads(response.body) if hasattr(response, "body") else response
    return sorted(s["id"] for s in payload.get("data", payload)["sessions"])


_ROUTES = pytest.mark.parametrize("list_ids", [_chat_init_ids, _chat_sessions_route_ids], ids=["chat-init", "sessions"])


@_ROUTES
@pytest.mark.asyncio
async def test_a_caller_with_no_ownership_records_gets_nothing(list_ids):
    assert await list_ids(NEWCOMER) == []


@_ROUTES
@pytest.mark.asyncio
async def test_a_principal_with_no_username_gets_nothing(list_ids):
    assert await list_ids(NAMELESS) == []


@_ROUTES
@pytest.mark.asyncio
async def test_a_caller_with_records_sees_only_their_own(list_ids):
    assert await list_ids(ALICE) == ["alice-1"]


def _calls(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn).lstrip())
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def test_both_routes_share_one_listing():
    """One ownership mechanism: chat-init and the chat sessions list call the same helper."""
    assert "list_user_sessions" in _calls(batch_jobs.get_chat_sessions)
    assert "list_user_sessions" in _calls(chat_sessions.list_sessions)
