# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An agent route takes the caller's role from the authenticated identity, never the request (#22143).

``/pause``, ``/resume``, ``/goal``, ``/execute_command`` and ``/command_approval`` each asked
``security_layer.check_permission`` about a client-supplied ``user_role``, so any caller could name itself ``admin``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.agent import router as agent_router
from auth_middleware import check_admin_permission, get_current_user


class _RecordingSecurityLayer:
    """Grants only the admin role, and records every role it is asked about."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def check_permission(self, role: str, permission: str, **kwargs) -> bool:
        self.asked.append(role)
        return role == "admin"

    def audit_log(self, *args, **kwargs) -> None:
        pass


def _client(session_role: str):
    app = FastAPI()
    app.include_router(agent_router, prefix="/api/agent")
    layer = _RecordingSecurityLayer()
    app.state.security_layer = layer
    app.state.orchestrator = MagicMock(pause_agent=AsyncMock(), resume_agent=AsyncMock())
    app.state.main_redis_client = MagicMock()
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": session_role}
    return TestClient(app), layer


_FORM_ROUTES = ["/api/agent/pause", "/api/agent/resume"]
_JSON_ROUTES = [
    ("/api/agent/goal", {"goal": "do it"}),
    ("/api/agent/execute_command", {"command": "ls"}),
    ("/api/agent/command_approval", {"task_id": "t1", "approved": True}),
]


@pytest.mark.parametrize("path", _FORM_ROUTES)
def test_non_admin_claiming_admin_in_form_is_refused(path):
    client, layer = _client("readonly")
    assert client.post(path, data={"user_role": "admin"}).status_code == 403
    assert layer.asked == ["readonly"]


@pytest.mark.parametrize(("path", "body"), _JSON_ROUTES)
def test_non_admin_claiming_admin_in_body_is_refused(path, body):
    client, layer = _client("readonly")
    assert client.post(path, json={**body, "user_role": "admin"}).status_code == 403
    assert layer.asked == ["readonly"]


@pytest.mark.parametrize("path", _FORM_ROUTES)
def test_admin_session_is_allowed(path):
    client, layer = _client("admin")
    with patch("api.agent.publish_event_safe", new=AsyncMock()):
        assert client.post(path).status_code == 200
    assert layer.asked == ["admin"]
