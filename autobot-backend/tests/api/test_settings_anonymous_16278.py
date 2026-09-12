# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An anonymous caller gets 401 from the core settings routes, through the REAL gate (#16278).

``api/settings_config_test.py`` proves the wiring by overriding
``check_admin_permission`` with a refusal. This proves the refusal itself. Under
pytest, ``auth_middleware`` is the conftest stub, so the override here is the
real function from ``real_auth_middleware``, and the only thing the test
controls is who that real code sees -- nobody, a member, or an admin.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import settings_config
from api.settings import router
from api.user_management.dependencies import get_db_session


async def _fake_session():
    yield MagicMock()


@pytest.fixture
def client(real_auth_middleware, monkeypatch):
    """The settings router behind the real admin gate; ``identity.user`` is who it sees."""
    identity = SimpleNamespace(user=None)
    middleware = SimpleNamespace(get_user_from_request=lambda _request: identity.user)
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    app = FastAPI()
    app.include_router(router, prefix="/api/settings")
    app.dependency_overrides[get_db_session] = _fake_session
    app.dependency_overrides[settings_config.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_an_anonymous_caller_gets_401(client, method):
    test_client, _ = client
    with patch.object(settings_config, "ConfigService") as config:
        response = test_client.request(method, "/api/settings/", json={"key": "value"} if method == "POST" else None)

    assert response.status_code == 401, response.text
    config.get_full_config.assert_not_called()
    config.save_full_config.assert_not_called()


def test_a_non_admin_gets_403(client):
    test_client, identity = client
    identity.user = {"username": "viewer", "role": "user"}
    with patch.object(settings_config, "ConfigService") as config:
        response = test_client.get("/api/settings/")

    assert response.status_code == 403, response.text
    config.get_full_config.assert_not_called()


def test_an_admin_writes_settings(client):
    """The control: the 401 and 403 above come from the gate, not from a broken harness.

    Only admission is judged here. The author the write records comes from the
    stub's ``get_current_user``; authorship is ``settings_revision_author_test.py``.
    """
    test_client, identity = client
    identity.user = {"username": "operator", "role": "admin"}
    revisions = MagicMock()
    revisions.return_value.create_revision = AsyncMock()
    with (
        patch.object(settings_config, "ConfigService") as config,
        patch.object(settings_config, "ConfigRevisionService", revisions),
    ):
        config.get_full_config.return_value = {}
        config.save_full_config.return_value = {"status": "saved"}
        response = test_client.post("/api/settings/", json={"key": "value"})

    assert response.status_code == 200, response.text
    config.save_full_config.assert_called_once()
