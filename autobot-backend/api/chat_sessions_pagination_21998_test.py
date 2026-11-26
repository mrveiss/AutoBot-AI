# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An out-of-range page/per_page is a client error (4xx) naming the range, not a 500 (#21998)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat_sessions as chat_sessions
from security.session_ownership import validate_session_ownership

SID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"


@pytest.fixture
def client(monkeypatch):
    manager = MagicMock()
    manager.get_session_message_count = AsyncMock(return_value=0)
    monkeypatch.setattr(chat_sessions, "get_chat_history_manager", lambda _r: manager)
    monkeypatch.setattr(chat_sessions, "fetch_session_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(chat_sessions, "log_request_context", MagicMock())
    app = FastAPI()
    app.include_router(chat_sessions.router, prefix="/api")
    app.dependency_overrides[validate_session_ownership] = lambda: {"valid": True}
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("query", ["per_page=200", "per_page=0", "page=0", "page=-1"])
def test_out_of_range_is_4xx_with_the_range_stated(client, query):
    response = client.get(f"/api/chat/sessions/{SID}?{query}")

    assert response.status_code == 400
    reason = response.json()["detail"]["error"]["details"]["reason"]
    assert reason == f"page must be >= 1 and per_page 1-{chat_sessions.CHAT_MESSAGES_MAX_PER_PAGE}"
    assert "page must be >= 1" in reason
    assert f"1-{chat_sessions.CHAT_MESSAGES_MAX_PER_PAGE}" in reason


def test_out_of_range_is_not_logged_as_a_server_fault(client, caplog):
    with caplog.at_level("WARNING"):
        client.get(f"/api/chat/sessions/{SID}?per_page=200")

    records = [r for r in caplog.records if "get_session_messages" in r.getMessage()]
    assert records
    assert all(r.levelname == "WARNING" for r in records)


@pytest.mark.parametrize("query", ["", "per_page=100", "page=2&per_page=1"])
def test_valid_request_is_200(client, query):
    assert client.get(f"/api/chat/sessions/{SID}?{query}").status_code == 200
