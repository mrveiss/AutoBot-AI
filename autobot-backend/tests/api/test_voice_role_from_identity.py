# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A voice route takes the caller's role from the authenticated identity, never the form (#22143).

``/listen``, ``/speak``, ``/synthesize`` and ``/clone-voice`` each asked ``security_layer.check_permission`` about a
``user_role`` form field, so any caller could name itself ``admin``, and ``/transcribe`` asked about a literal
``"user"``. All five now use the session role and ignore that field.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.voice import router as voice_router
from auth_middleware import check_admin_permission, get_current_user
from security_layer import SecurityLayer
from testkit.canonical_gate import no_user_middleware, real_admin_gate

_AUTHENTICATED_ROLE = "readonly"
_CLAIMED_ROLE = "admin"


class _ListeningInterface:
    """A voice interface whose recogniser succeeds, so an allowed ``/listen`` reaches a 200."""

    async def listen_and_convert_to_text(self) -> dict:
        return {"status": "success", "text": "hello"}


class _RecordingSecurityLayer:
    """Grants only the admin role, and records every role it is asked about."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def check_permission(self, role: str, permission: str) -> bool:
        self.asked.append(role)
        return role == "admin"

    def audit_log(self, *args, **kwargs) -> None:
        pass


@pytest.fixture
def harness():
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    layer = _RecordingSecurityLayer()
    app.state.security_layer = layer
    app.state.voice_interface = object()
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u1", "role": _AUTHENTICATED_ROLE}
    return TestClient(app), layer


_ROUTES = [
    ("/api/voice/listen", {}, None),
    ("/api/voice/speak", {"text": "hi"}, None),
    ("/api/voice/synthesize", {"text": "hi"}, None),
    ("/api/voice/clone-voice", {"text": "hi"}, {"reference_audio": ("r.wav", b"RIFF", "audio/wav")}),
    ("/api/voice/transcribe", {}, {"audio": ("a.webm", b"x", "audio/webm")}),
]


@pytest.mark.parametrize(("path", "data", "files"), _ROUTES)
def test_non_admin_claiming_admin_is_refused(harness, path, data, files):
    client, layer = harness
    response = client.post(path, data={**data, "user_role": _CLAIMED_ROLE}, files=files)
    assert response.status_code == 403
    assert layer.asked == [_AUTHENTICATED_ROLE]


def test_admin_session_is_allowed_and_audited_as_admin(harness):
    """The converse: the session role is what is consulted, so an admin session is not refused."""
    client, layer = harness
    client.app.dependency_overrides[get_current_user] = lambda: {"user_id": "a1", "role": "admin"}
    client.app.state.voice_interface = _ListeningInterface()
    response = client.post("/api/voice/listen", data={"user_role": "readonly"})
    assert response.status_code == 200
    assert response.json()["text"] == "hello"
    assert layer.asked == ["admin"]


def _real_gate_client(user):
    """A client whose ``check_admin_permission`` is the REAL gate, seeing *user* (None = anonymous)."""
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    app.state.security_layer = _RecordingSecurityLayer()
    app.state.voice_interface = object()
    if user is None:
        middleware = no_user_middleware()
    else:
        middleware = MagicMock()
        middleware.get_user_from_request.side_effect = lambda request: user
    app.dependency_overrides[get_current_user] = lambda: user
    return app, middleware


@pytest.mark.parametrize(("user", "status"), [(None, 401), ({"user_id": "u", "role": "user"}, 403)])
def test_real_admin_gate_refuses_anonymous_and_non_admin(user, status):
    app, middleware = _real_gate_client(user)
    with real_admin_gate(middleware) as wire:
        client = wire(TestClient(app))
        response = client.post("/api/voice/speak", data={"text": "hi", "user_role": _CLAIMED_ROLE})
    assert response.status_code == status
    assert app.state.security_layer.asked == []


class _RealRecordingLayer(SecurityLayer):
    """The real RBAC resolver, recording each (role, action, verdict) it answers."""

    def __init__(self) -> None:
        super().__init__()
        self.verdicts: list[tuple[str, str, bool]] = []

    def check_permission(self, user_role, action_type, resource=None):
        verdict = super().check_permission(user_role, action_type, resource)
        self.verdicts.append((user_role, action_type, verdict))
        return verdict

    def audit_log(self, *args, **kwargs) -> None:
        pass


@pytest.mark.parametrize(("path", "data", "files"), _ROUTES)
def test_superadmin_holds_admins_voice_grants_on_every_route(harness, path, data, files):
    """#19125: superadmin is the highest admin, so the real resolver must grant it what admin has."""
    client, _ = harness
    layer = _RealRecordingLayer()
    client.app.state.security_layer = layer
    client.app.dependency_overrides[get_current_user] = lambda: {"user_id": "s1", "role": "superadmin"}
    client.post(path, data=data, files=files)
    assert [(role, ok) for role, _action, ok in layer.verdicts] == [("superadmin", True)]
