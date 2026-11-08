# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PUT /chat/sessions/{id} writes through the manager's real API (#20928).

The route used to call ``update_session(session_id=, title=, metadata=)`` on a manager whose
method takes ``(session_id, updates)`` and returns a bool, so it raised ``TypeError`` on every
request. A real ``ChatHistoryManager`` writing under ``tmp_path`` is used: a mock accepting any
arguments would have passed against the broken call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import api.chat_sessions as chat_sessions
from api.schemas_chat import SessionUpdate
from chat_history import ChatHistoryManager
from exceptions import InternalError, ResourceNotFoundError

SID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"


@pytest.fixture
def history(tmp_path, monkeypatch):
    chats = tmp_path / "chats"
    chats.mkdir()
    manager = ChatHistoryManager(history_file=str(tmp_path / "history.json"), use_redis=False)
    manager.redis_client = None
    monkeypatch.setattr(manager, "_get_chats_directory", lambda: str(chats))
    monkeypatch.setattr(chat_sessions, "get_chat_history_manager", lambda _r: manager)
    monkeypatch.setattr(chat_sessions, "publish_session_updated", AsyncMock())
    for name in ("log_chat_event", "log_request_context"):
        monkeypatch.setattr(chat_sessions, name, MagicMock())
    return manager


async def _put(body: SessionUpdate, sid: str = SID):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    return await chat_sessions.update_session.__wrapped__(sid, body, request, ownership={"valid": True})


@pytest.mark.asyncio
async def test_put_applies_title_and_merges_metadata(history):
    await history.create_session(session_id=SID, title="old", metadata={"owner": "alice"})

    response = await _put(SessionUpdate(title="new title", metadata={"color": "red"}))

    stored = await history.get_session(SID)
    assert stored["name"] == "new title"
    assert stored["metadata"]["color"] == "red"
    assert stored["metadata"]["owner"] == "alice"  # a merge: server-written keys survive
    assert response.status_code == 200
    assert b"new title" in response.body


@pytest.mark.asyncio
async def test_put_on_absent_session_is_not_found(history):
    with pytest.raises(ResourceNotFoundError):
        await _put(SessionUpdate(title="x"))


@pytest.mark.asyncio
async def test_put_failed_write_is_an_error_not_success(history, monkeypatch):
    await history.create_session(session_id=SID, title="old")

    async def _refuse(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(history, "_write_session_to_storage", _refuse)

    with pytest.raises(InternalError):
        await _put(SessionUpdate(title="new"))
