# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Delete, rename and reset are owner-only; export follows read access (#21898).

The routes run through the real FastAPI dependency chain: ``validate_session_ownership`` is patched to return a
given ``reason`` and everything the route would do afterwards is a recorded mock, so "deletes nothing" is asserted.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat_session_sharing as sharing
import api.chat_sessions as chat_sessions
from api.chat_session_sharing import validate_session_owner
from api.schemas_chat import ChatResetRequest
from security import session_shares

SID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"
REFUSAL = "You do not have permission to access this conversation"
NON_OWNER_REASONS = ["shared_access", "org_admin", "log_only_mode"]


def _ownership(reason):
    return {"authorized": True, "user_data": {"username": "bob"}, "reason": reason}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(chat_sessions.router, prefix="/api")
    for name in ("log_chat_event", "log_request_context", "audit_record"):
        monkeypatch.setattr(chat_sessions, name, MagicMock())
    monkeypatch.setattr(
        chat_sessions,
        "get_chat_history_manager",
        lambda _r: MagicMock(get_session_message_count=AsyncMock(return_value=0)),
    )
    monkeypatch.setattr(chat_sessions, "get_auth_middleware", lambda: MagicMock())
    monkeypatch.setattr(chat_sessions, "publish_session_deleted", AsyncMock())
    monkeypatch.setattr(chat_sessions, "_emit_session_destroy", AsyncMock())
    monkeypatch.setattr(chat_sessions, "delete_session_or_refer", AsyncMock())
    monkeypatch.setattr(chat_sessions, "_perform_all_session_cleanup", AsyncMock(return_value=({}, {}, {}, {}, {})))
    monkeypatch.setattr(chat_sessions, "_build_delete_session_response", lambda *a, **k: {"deleted": True})
    return TestClient(app)


def _as(reason):
    return patch.object(sharing, "validate_session_ownership", AsyncMock(return_value=_ownership(reason)))


@pytest.mark.parametrize("reason", sorted(session_shares.OWNER_REASONS))
def test_owner_can_delete(client, reason):
    with _as(reason):
        response = client.delete(f"/api/chat/sessions/{SID}")
    assert response.status_code == 200
    chat_sessions.delete_session_or_refer.assert_awaited_once()


@pytest.mark.parametrize("reason", NON_OWNER_REASONS)
def test_non_owner_delete_is_refused_and_deletes_nothing(client, reason):
    with _as(reason):
        response = client.delete(f"/api/chat/sessions/{SID}")
    assert response.status_code == 403
    assert response.json()["detail"] == REFUSAL
    chat_sessions.delete_session_or_refer.assert_not_awaited()
    chat_sessions._perform_all_session_cleanup.assert_not_awaited()


@pytest.mark.parametrize("reason", NON_OWNER_REASONS)
def test_non_owner_cannot_rename(client, reason):
    with _as(reason):
        response = client.put(f"/api/chat/sessions/{SID}", json={"title": "x"})
    assert response.status_code == 403


@pytest.mark.parametrize("reason", NON_OWNER_REASONS)
@pytest.mark.asyncio
async def test_non_owner_cannot_reset(reason):
    request = MagicMock()
    clear = AsyncMock()
    with (
        patch.object(chat_sessions, "validate_session_ownership", AsyncMock(return_value=_ownership(reason))),
        patch.object(chat_sessions, "_clear_session_messages", clear),
        patch.object(chat_sessions, "get_chat_history_manager", return_value=MagicMock()),
        pytest.raises(Exception) as err,
    ):
        await chat_sessions.reset_chat.__wrapped__(request, ChatResetRequest(session_id=SID, clear_context=True))
    assert err.value.status_code == 403
    clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_dependency_passes_owner_reasons_only():
    with patch.object(sharing, "validate_session_ownership", AsyncMock(return_value=_ownership("owner_match"))):
        assert (await validate_session_owner(SID, MagicMock()))["reason"] == "owner_match"


@pytest.mark.parametrize("reason", ["owner_match", "shared_access", "org_admin"])
def test_participant_can_still_export(client, reason, monkeypatch):
    monkeypatch.setattr(chat_sessions, "_export_session_data_or_raise", AsyncMock(return_value='{"m": []}'))
    route = next(r for r in chat_sessions.router.routes if r.path.endswith("/export"))
    dep = next(d.call for d in route.dependant.dependencies if d.call.__name__ != "get_current_user")
    assert dep is chat_sessions.validate_session_ownership  # export keeps the read-access dependency
    client.app.dependency_overrides[dep] = lambda: _ownership(reason)
    response = client.get(f"/api/chat/sessions/{SID}/export")
    assert response.status_code == 200


@pytest.fixture
def chats_client(client):
    """The alias route DELETE /chats/{id}: its own read-access dependency, then the canonical delete."""
    import api.chat as chat_api
    from auth_middleware import get_current_user

    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"username": "bob"}
    return TestClient(app), chat_api


@pytest.mark.parametrize("reason", NON_OWNER_REASONS)
def test_chats_alias_refuses_non_owner_and_deletes_nothing(chats_client, reason):
    http, chat_api = chats_client
    with patch.object(chat_api, "validate_session_ownership", AsyncMock(return_value=_ownership(reason))):
        response = http.delete(f"/api/chats/{SID}")
    assert response.status_code == 403
    assert response.json()["detail"] == REFUSAL
    chat_sessions.delete_session_or_refer.assert_not_awaited()
    chat_sessions._perform_all_session_cleanup.assert_not_awaited()


@pytest.mark.parametrize("reason", sorted(session_shares.OWNER_REASONS))
def test_chats_alias_lets_the_owner_delete(chats_client, reason):
    http, chat_api = chats_client
    with patch.object(chat_api, "validate_session_ownership", AsyncMock(return_value=_ownership(reason))):
        response = http.delete(f"/api/chats/{SID}")
    assert response.status_code == 200, response.text
    chat_sessions.delete_session_or_refer.assert_awaited_once()
