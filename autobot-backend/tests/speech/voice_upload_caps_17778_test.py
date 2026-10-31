# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every audio upload read in ``api/voice.py`` is byte-capped (HTTP 413), not just the multimodal route (#17778)."""

from unittest.mock import create_autospec

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.voice import router as voice_router
from security_layer import SecurityLayer


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(voice_router, prefix="/api/voice")
    security = create_autospec(SecurityLayer, instance=True, spec_set=True)
    security.check_permission.return_value = True
    app.state.security_layer = security
    return TestClient(app, raise_server_exceptions=True)


@pytest.mark.parametrize(
    "path, field, extra",
    [
        ("/api/voice/transcribe", "audio", {}),
        ("/api/voice/voices/create", "audio", {"name": "n"}),
        ("/api/voice/clone-voice", "reference_audio", {"text": "hi"}),
    ],
)
def test_an_oversized_upload_is_413_before_any_work(monkeypatch, path, field, extra):
    monkeypatch.setenv("AUTOBOT_AUDIO_UPLOAD_MAX_BYTES", "16")
    response = _client().post(path, files={field: ("clip.wav", b"x" * 17, "audio/wav")}, data=extra)
    assert response.status_code == 413, response.text
