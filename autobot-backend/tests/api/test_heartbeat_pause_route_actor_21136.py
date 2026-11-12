# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pause, resume and terminate take the actor from the authenticated caller, never the body (#21136)."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import heartbeat
from api.schemas_heartbeat import HeartbeatConfigResponse
from models.heartbeat import HeartbeatStatus

_BASE = "/api/heartbeat/a1"
_CALLER = {"id": "principal-7", "username": "alice", "role": "admin"}
_STAMP = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _state() -> SimpleNamespace:
    """Every attribute ``_state_to_response`` reads, typed as the ORM row types them."""
    return SimpleNamespace(
        agent_id="a1",
        heartbeat_enabled=True,
        status=HeartbeatStatus.ACTIVE.value,
        paused_reason=None,
        paused_at=None,
        paused_by=None,
        error_detail=None,
        error_at=None,
        error_code=None,
        heartbeat_interval_seconds=60,
        max_run_duration_seconds=3600,
        current_task_id=None,
        last_heartbeat_at=_STAMP,
        session_params={},
        extra=None,
        created_at=_STAMP,
        updated_at=_STAMP,
    )


@pytest.fixture
def harness(real_auth_middleware, monkeypatch):
    """The real router and the real auth dependency; only the stores are faked."""
    identity = SimpleNamespace(user=_CALLER)

    async def _no_token(_request):
        return None

    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: identity.user,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)

    audits: list = []

    async def _record(event):
        audits.append(event.actor_id)
        return True

    state = _state()
    session = MagicMock(commit=AsyncMock(), refresh=AsyncMock())
    scheduler = MagicMock(disable_agent=AsyncMock(), enable_agent=AsyncMock())
    get_state = AsyncMock(return_value=state)
    names = AsyncMock(return_value=None)
    monkeypatch.setattr(heartbeat, "record_committed", _record)
    monkeypatch.setattr(heartbeat, "_get_or_create_state", get_state)
    monkeypatch.setattr(heartbeat, "_paused_by_name", names)
    app = FastAPI()
    app.include_router(heartbeat.router, prefix="/api/heartbeat")
    app.dependency_overrides[heartbeat.get_current_user] = real_auth_middleware.get_current_user
    app.dependency_overrides[heartbeat.get_db_session] = lambda: session
    app.dependency_overrides[heartbeat._get_scheduler] = lambda: scheduler
    return SimpleNamespace(
        client=TestClient(app),
        identity=identity,
        state=state,
        audits=audits,
        session=session,
        scheduler=scheduler,
        get_state=get_state,
        names=names,
    )


def test_pause_ignores_forged_body_actor(harness) -> None:
    response = harness.client.post(f"{_BASE}/pause", json={"reason": "r", "paused_by": "system:forged"})

    assert response.status_code == 200
    # Fails if the route used the body: the state write would carry "system:forged".
    assert harness.state.paused_by == "principal-7"
    # Fails if the audit named the body's value.
    assert harness.audits == ["principal-7"]
    body = HeartbeatConfigResponse.model_validate(response.json())
    assert (body.agent_id, body.status, body.paused_reason) == ("a1", HeartbeatStatus.PAUSED.value, "r")
    assert body.paused_by == "principal-7"
    assert body.paused_at is not None
    harness.names.assert_awaited_once_with(harness.session, "principal-7")
    harness.scheduler.disable_agent.assert_awaited_once_with("a1")


_ROUTES = [
    pytest.param("pause", {"reason": "r", "paused_by": "system:forged"}, id="pause"),
    pytest.param("resume", {}, id="resume"),
    pytest.param("terminate", {"reason": "r"}, id="terminate"),
]


@pytest.mark.parametrize(("action", "payload"), _ROUTES)
def test_an_anonymous_caller_is_refused_and_nothing_is_written(harness, action: str, payload: dict) -> None:
    harness.identity.user = None

    response = harness.client.post(f"{_BASE}/{action}", json=payload)

    assert response.status_code == 401
    assert harness.audits == []
    harness.get_state.assert_not_awaited()
    harness.session.commit.assert_not_awaited()
    harness.scheduler.disable_agent.assert_not_awaited()
    harness.scheduler.enable_agent.assert_not_awaited()
    assert (harness.state.status, harness.state.paused_by) == (HeartbeatStatus.ACTIVE.value, None)
