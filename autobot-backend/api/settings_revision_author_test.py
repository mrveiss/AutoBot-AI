# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two ``settings.py`` writes name who made them in their revision (#16278).

``POST /sync`` and ``PATCH /hardware-priority`` recorded the literal ``"admin"``
after the core config routes in ``settings_config.py`` had moved to the real
caller. Both now take the actor from ``require_settings_admin``. The stub
session's user is ``"test-user"`` (``testkit/auth_middleware_stub.py``).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import settings, settings_config
from api.user_management.dependencies import get_db_session

_ORDER = ["npu", "gpu", "cpu"]
_WRITES = [
    ("POST", "/api/settings/sync", {"settings": {"chat": {"k": "v"}}}),
    ("PATCH", "/api/settings/hardware-priority", {"priority_order": _ORDER}),
]


async def _fake_session():
    yield MagicMock()


def _recorded_author(method: str, path: str, body: dict, *, internal_key: bool) -> str:
    app = FastAPI()
    app.include_router(settings.router, prefix="/api/settings")
    app.dependency_overrides[get_db_session] = _fake_session
    revisions = MagicMock()
    revisions.return_value.create_revision = AsyncMock()
    hardware = MagicMock(current_config={"priority_order": [SimpleNamespace(value=v) for v in _ORDER]})
    with (
        patch.object(settings, "ConfigService") as config,
        patch.object(settings, "ConfigRevisionService", revisions),
        patch.object(settings, "_atomic_write_json", AsyncMock()),
        patch("hardware_acceleration.get_hardware_acceleration_manager", return_value=hardware),
        patch.object(settings_config, "verify_internal_api_key", return_value=internal_key),
    ):
        config.get_full_config.return_value = {}
        response = TestClient(app).request(method, path, json=body)
    assert response.status_code == 200, response.text
    return revisions.return_value.create_revision.await_args.kwargs["created_by"]


@pytest.mark.parametrize(("method", "path", "body"), _WRITES)
def test_an_admin_session_is_recorded_by_username(method, path, body):
    assert _recorded_author(method, path, body, internal_key=False) == "test-user"


@pytest.mark.parametrize(("method", "path", "body"), _WRITES)
def test_the_internal_service_key_is_recorded_as_the_service(method, path, body):
    assert _recorded_author(method, path, body, internal_key=True) == settings_config.INTERNAL_SERVICE_ACTOR
