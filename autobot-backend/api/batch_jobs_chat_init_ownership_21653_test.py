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

The ownership store is doubled the way ``tests/test_chat_session_ownership_failclosed.py``
doubles it: ``_build_ownership_validator`` patched to a validator with a per-user map.
"""

import ast
import inspect
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


def _validator():
    v = MagicMock()
    v.get_user_sessions = AsyncMock(side_effect=lambda username: _OWNED.get(username, []))
    return v


def _request():
    manager = MagicMock()
    manager.list_sessions_fast = AsyncMock(return_value=[dict(s) for s in _SESSIONS])
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(chat_history_manager=manager)))


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


def _calls(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn).lstrip())
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def test_both_routes_share_one_listing():
    """One ownership mechanism: chat-init and the chat sessions list call the same helper."""
    assert "list_user_sessions" in _calls(batch_jobs.get_chat_sessions)
    assert "list_user_sessions" in _calls(chat_sessions.list_sessions)
