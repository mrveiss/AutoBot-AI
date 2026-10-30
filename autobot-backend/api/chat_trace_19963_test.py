# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /chat/sessions/{id}/trace: owner-or-admin, and a non-owner sees what a missing session shows (#19963).

The route is mounted through a real request and the REAL ownership validator runs (STRICT
posture); only the session store and the approval lookups are replaced.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api import chat_trace
from auth_middleware import get_current_user
from models.command_execution import CommandExecution, CommandState
from testkit.canonical_gate import install_canonical_resolver

URL = "/chat/sessions/{}/trace"

HELD_TURN = [
    {"id": "u1", "sender": "user", "text": "ls", "messageType": "default", "metadata": {}},
    {
        "id": "a1",
        "sender": "assistant",
        "text": "approval needed for ls -la",
        "messageType": "command_approval_request",
        "metadata": {"command": "ls -la", "terminal_session_id": "term-1", "iteration": 1},
    },
]


def _as_user(monkeypatch, username, owner, messages, role="user"):
    install_canonical_resolver(
        monkeypatch,
        "security.session_posture.resolve_human_user",
        MagicMock(get_user_from_request=lambda _r: {"username": username, "role": role}),
    )
    history = MagicMock(get_session_owner=AsyncMock(return_value=owner), load_session=AsyncMock(return_value=messages))
    monkeypatch.setattr("utils.chat_utils.get_chat_history_manager", lambda _r: history)
    monkeypatch.setattr(chat_trace, "get_chat_history_manager", lambda _r: history)
    command = CommandExecution(terminal_session_id="term-1", chat_id="s", command="ls -la")
    command.state = CommandState.PENDING_APPROVAL
    queue = SimpleNamespace(get_chat_commands=AsyncMock(return_value=[command]))
    monkeypatch.setattr("services.command_execution_queue.get_command_queue", lambda: queue)


async def _get(session_id):
    app = FastAPI()
    app.include_router(chat_trace.router)
    app.dependency_overrides[get_current_user] = lambda: {"username": "bob"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(URL.format(session_id))


@pytest.mark.asyncio
async def test_owner_sees_the_held_call_with_its_current_approval_state(monkeypatch):
    _as_user(monkeypatch, "alice", "alice", HELD_TURN)

    response = await _get("s")

    assert response.status_code == 200
    call = response.json()["data"]["turns"][0]["iterations"][0]["tool_calls"][0]
    assert call["verdict"] == "held"
    assert call["approval"] == {"id": "term-1", "kind": "terminal", "state": "pending_approval"}
    assert call["result_returned"] == "no"


@pytest.mark.asyncio
async def test_admin_may_read_a_session_they_do_not_own(monkeypatch):
    _as_user(monkeypatch, "root", "alice", HELD_TURN, role="admin")

    assert (await _get("s")).status_code == 200


@pytest.mark.asyncio
async def test_a_non_owner_gets_the_response_a_missing_session_gets(monkeypatch):
    _as_user(monkeypatch, "bob", "alice", HELD_TURN)
    not_yours = await _get("alices-chat")
    _as_user(monkeypatch, "bob", None, [])
    missing = await _get("no-such-chat")

    assert not_yours.status_code == missing.status_code == 404
    assert not_yours.content == missing.content
