# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routes that raised ValidationError for non-validation faults answer the right status (#21998)."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.chat_folders as chat_folders
import api.chat_sessions as chat_sessions
from security.session_ownership import validate_session_ownership

SID = "6a1d0b6f-2c3d-4e4f-9a01-1b2c3d4e5f60"


def _app(user: dict) -> FastAPI:
    app = FastAPI()
    app.include_router(chat_sessions.router, prefix="/api")
    app.include_router(chat_folders.router, prefix="/api")
    app.dependency_overrides[validate_session_ownership] = lambda: {"valid": True}
    app.dependency_overrides[chat_sessions.get_current_user] = lambda: user
    app.dependency_overrides[chat_folders.get_current_user] = lambda: user
    return app


@pytest.fixture
def make_client(monkeypatch):
    manager = MagicMock()
    monkeypatch.setattr(chat_sessions, "get_chat_history_manager", lambda _r: manager)
    monkeypatch.setattr(chat_sessions, "log_request_context", MagicMock())

    def _make(user=None, auth_user="unset"):
        middleware = MagicMock()
        middleware.get_user_from_request.return_value = user if auth_user == "unset" else auth_user
        monkeypatch.setattr(chat_sessions, "get_auth_middleware", lambda: middleware)
        return TestClient(_app(user or {"username": "u", "role": "user"}), raise_server_exceptions=False), manager

    return _make


def test_scoped_listing_without_a_user_is_401(make_client):
    client, _ = make_client(auth_user=None)
    assert client.get("/api/chat/sessions?scope=org").status_code == 401


def test_org_listing_by_a_non_admin_is_403(make_client, monkeypatch):
    monkeypatch.setattr(chat_sessions, "_build_ownership_validator", MagicMock())
    monkeypatch.setattr("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=MagicMock()))
    client, _ = make_client(user={"username": "u", "role": "user", "org_id": "o1"})
    assert client.get("/api/chat/sessions?scope=org").status_code == 403


def test_clearing_checkpoints_by_a_non_admin_is_403(make_client):
    client, _ = make_client(user={"username": "u", "role": "user"})
    assert client.delete(f"/api/sessions/{SID}/checkpoints").status_code == 403


def test_corrupted_session_data_is_5xx_logged_at_error(make_client, caplog):
    client, manager = make_client(user={"username": "u", "role": "user"})
    manager.get_session_messages = AsyncMock(side_effect=ValueError("bad json"))
    with caplog.at_level(logging.WARNING):
        response = client.get(f"/api/chat/sessions/{SID}")
    assert response.status_code == 500
    boundary = [r for r in caplog.records if "get_session_messages" in r.getMessage()]
    assert boundary and all(r.levelno == logging.ERROR for r in boundary)


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/chat/folders", {"name": "f", "parent_id": "missing"}),
        ("put", "/api/chat/folders/f1", {"parent_id": "missing"}),
    ],
)
def test_missing_parent_folder_is_404(make_client, monkeypatch, method, path, body):
    redis = MagicMock()
    redis.get = AsyncMock(return_value='[{"id": "f1", "name": "x"}]')
    monkeypatch.setattr("autobot_shared.redis_client.get_redis_client", AsyncMock(return_value=redis))
    client, _ = make_client(user={"username": "u", "role": "user"})
    assert getattr(client, method)(path, json=body).status_code == 404
