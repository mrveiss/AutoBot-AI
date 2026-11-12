# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pause route takes the actor from the authenticated session, never the body (#21136)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import heartbeat
from models.heartbeat import HeartbeatStatus

_URL = "/api/heartbeat/a1/pause"


@pytest.fixture
def client(real_auth_middleware, monkeypatch):
    async def _no_token(_request):
        return None

    caller = {"id": "principal-7", "username": "alice", "role": "admin"}
    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: caller,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    audits: list = []

    async def _record(event):
        audits.append(event.actor_id)
        return True

    state = SimpleNamespace(
        status=HeartbeatStatus.ACTIVE.value,
        paused_by=None,
        paused_reason=None,
        paused_at=None,
        heartbeat_interval_seconds=60,
    )
    monkeypatch.setattr(heartbeat, "record_committed", _record)
    monkeypatch.setattr(heartbeat, "_get_or_create_state", AsyncMock(return_value=state))
    monkeypatch.setattr(heartbeat, "_state_response", AsyncMock(return_value={}))
    app = FastAPI()
    app.include_router(heartbeat.router, prefix="/api/heartbeat")
    app.dependency_overrides[heartbeat.get_current_user] = real_auth_middleware.get_current_user
    app.dependency_overrides[heartbeat.get_db_session] = lambda: MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    app.dependency_overrides[heartbeat._get_scheduler] = lambda: MagicMock(disable_agent=AsyncMock())
    return TestClient(app), state, audits


def test_pause_ignores_forged_body_actor(client) -> None:
    test_client, state, audits = client
    response = test_client.post(_URL, json={"reason": "r", "paused_by": "system:forged"})
    assert response.status_code == 200
    assert state.paused_by == "principal-7"
    assert audits == ["principal-7"]
