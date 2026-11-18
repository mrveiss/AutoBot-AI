# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`DELETE /chats/{chat_id}` must actually delete the session (#18316).

It called the async `delete_session` without `await`, so it answered 200 and the
session survived. It now delegates to the canonical session-delete logic. These
tests run the real canonical function against an in-memory history manager and
assert on whether the session still exists afterwards.
"""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import chat as chat_api
from api import chat_sessions


class _FakeHistory:
    def __init__(self, sessions):
        self.sessions = set(sessions)

    async def get_session_message_count(self, session_id):
        return 0

    async def delete_session(self, session_id):
        if session_id not in self.sessions:
            return False
        self.sessions.discard(session_id)
        return True


def _request():
    request = MagicMock()
    request.client.host = "127.0.0.1"
    request.app.state.context = {}
    return request


async def _call(history, chat_id, ownership=None):
    cleanup = ({}, {}, {}, {}, {})
    with ExitStack() as stack:
        stack.enter_context(patch.object(chat_sessions, "get_chat_history_manager", return_value=history))
        stack.enter_context(
            patch.object(chat_sessions, "_perform_all_session_cleanup", AsyncMock(return_value=cleanup))
        )
        stack.enter_context(patch.object(chat_sessions, "_emit_session_destroy", AsyncMock()))
        stack.enter_context(patch.object(chat_sessions, "publish_session_deleted", AsyncMock()))
        stack.enter_context(patch.object(chat_sessions, "audit_record", MagicMock()))
        stack.enter_context(patch.object(chat_sessions, "get_auth_middleware", MagicMock()))
        return await chat_api.delete_chat_by_id(
            chat_id=chat_id,
            current_user={"username": "alice"},
            request=_request(),
            ownership=ownership or {"authorized": True},
        )


@pytest.mark.asyncio
async def test_the_session_is_gone_afterwards():
    history = _FakeHistory({"c1", "c2"})
    response = await _call(history, "c1")
    body = json.loads(response.body)
    assert response.status_code == 200
    assert body["data"] == {"session_id": "c1", "deleted": True}
    assert history.sessions == {"c2"}


@pytest.mark.asyncio
async def test_contrast_the_old_unawaited_call_deletes_nothing():
    """Reproduces the pre-fix behaviour: a coroutine that is never awaited."""
    history = _FakeHistory({"c1"})
    history.delete_session("c1").close()  # what `delete_session(...)` without await does
    assert history.sessions == {"c1"}


@pytest.mark.asyncio
async def test_a_missing_session_matches_the_canonical_route():
    history = _FakeHistory(set())
    with pytest.raises(Exception) as chat_exc:
        await _call(history, "nope")
    with pytest.raises(Exception) as canon_exc:
        with patch.object(chat_sessions, "get_chat_history_manager", return_value=history):
            with patch.object(chat_sessions, "_perform_all_session_cleanup", AsyncMock(return_value=({},) * 5)):
                await chat_sessions.delete_session(
                    session_id="nope", request=_request(), ownership={"authorized": True}
                )
    assert type(chat_exc.value) is type(canon_exc.value)
    assert getattr(chat_exc.value, "status_code", None) == getattr(canon_exc.value, "status_code", None)


@pytest.mark.asyncio
async def test_a_non_owner_is_refused_and_nothing_is_deleted():
    """The ownership Depends is declared on the route and rejects before the handler runs."""
    from fastapi.routing import APIRoute

    route = next(
        r
        for r in chat_api.router.routes
        if isinstance(r, APIRoute) and r.path == "/chats/{chat_id}" and "DELETE" in r.methods
    )
    dependants = {d.call for d in route.dependant.dependencies}
    assert chat_api.validate_chat_ownership in dependants

    def _forbidden(*_a, **_k):
        raise HTTPException(status_code=403, detail="not your session")

    with patch.object(chat_api, "validate_chat_ownership", side_effect=_forbidden):
        with pytest.raises(HTTPException) as excinfo:
            await chat_api.validate_chat_ownership("c1", _request())
    assert excinfo.value.status_code == 403
