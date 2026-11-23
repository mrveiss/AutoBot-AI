# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A voice route takes the caller's role from the authenticated identity, never the form (#22143).

``/listen``, ``/speak``, ``/synthesize`` and ``/clone-voice`` each asked ``security_layer.check_permission`` about a
``user_role`` form field, so any caller could name itself ``admin``. Each now ignores that field.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.voice import router as voice_router
from auth_middleware import check_admin_permission, get_current_user

_AUTHENTICATED_ROLE = "readonly"
_CLAIMED_ROLE = "admin"


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
]


@pytest.mark.parametrize(("path", "data", "files"), _ROUTES)
def test_non_admin_claiming_admin_is_refused(harness, path, data, files):
    client, layer = harness
    response = client.post(path, data={**data, "user_role": _CLAIMED_ROLE}, files=files)
    assert response.status_code == 403
    assert layer.asked == [_AUTHENTICATED_ROLE]
