# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end tests of the admin gate on the core config routes (#16278).

Under test, ``auth_middleware`` is a stub whose ``check_admin_permission``
admits every caller (``testkit/auth_middleware_stub.py``). So these tests
supply the refusals the real gate raises by overriding it: 401 with no user,
403 for a non-admin (``auth_middleware.py:972``).

What they prove is the wiring:

- every config route runs the gate before its handler;
- a refusal stops the handler before it reads or writes config;
- an admitted write records who made it.

The refusal itself, through the real gate with a genuinely anonymous caller,
is ``tests/api/test_settings_anonymous_16278.py``. The deployed backend's 401
for an anonymous ``GET /api/settings/`` is host evidence, recorded on #16278.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import settings_config
from api.settings import router
from api.user_management.dependencies import get_db_session

_READ_PATHS = ("/api/settings/", "/api/settings/settings", "/api/settings/backend", "/api/settings/config")
_WRITE_PATHS = ("/api/settings/", "/api/settings/settings", "/api/settings/backend", "/api/settings/config")
_CLEAR_CACHE_PATH = "/api/settings/clear-cache"


async def _fake_session():
    yield MagicMock()


def _refusing(status_code: int):
    """Stand in for ``check_admin_permission``, raising the refusal the real gate raises."""

    def _gate():
        raise HTTPException(status_code=status_code, detail="refused by the test gate")

    return _gate


def _client(gate=None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/settings")
    app.dependency_overrides[get_db_session] = _fake_session
    if gate is not None:
        app.dependency_overrides[settings_config.check_admin_permission] = gate
    return TestClient(app)


@pytest.mark.parametrize("status_code", [401, 403])
class TestARefusedCallerNeverReachesConfig:
    """401 (no user) and 403 (not an admin) both stop a request before the handler runs."""

    def test_reads_are_refused(self, status_code):
        with patch.object(settings_config, "ConfigService") as config:
            client = _client(_refusing(status_code))
            for path in _READ_PATHS:
                assert client.get(path).status_code == status_code, path
        config.get_full_config.assert_not_called()
        config.get_backend_settings.assert_not_called()

    def test_writes_are_refused(self, status_code):
        with (
            patch.object(settings_config, "ConfigService") as config,
            patch.object(settings_config, "ConfigRevisionService") as revisions,
        ):
            client = _client(_refusing(status_code))
            for path in _WRITE_PATHS:
                assert client.post(path, json={"key": "value"}).status_code == status_code, path
            assert client.post(_CLEAR_CACHE_PATH).status_code == status_code
        config.save_full_config.assert_not_called()
        config.update_backend_settings.assert_not_called()
        config.clear_cache.assert_not_called()
        revisions.assert_not_called()


class TestAnAdmittedWriteRecordsItsAuthor:
    """Each revision names who made the write, not the literal ``"admin"`` every write used to record."""

    @staticmethod
    def _recorded_author(*, internal_key: bool) -> str:
        revisions = MagicMock()
        revisions.return_value.create_revision = AsyncMock()
        with (
            patch.object(settings_config, "ConfigService") as config,
            patch.object(settings_config, "ConfigRevisionService", revisions),
            patch.object(settings_config, "verify_internal_api_key", return_value=internal_key),
        ):
            config.get_full_config.return_value = {}
            config.save_full_config.return_value = {"status": "saved"}
            response = _client().post("/api/settings/", json={"key": "value"})
        assert response.status_code == 200, response.text
        return revisions.return_value.create_revision.await_args.kwargs["created_by"]

    def test_an_admin_session_is_recorded_by_username(self):
        # The stub session's user is "test-user" (testkit/auth_middleware_stub.py).
        assert self._recorded_author(internal_key=False) == "test-user"

    def test_the_internal_service_key_is_recorded_as_the_service(self):
        assert self._recorded_author(internal_key=True) == settings_config.INTERNAL_SERVICE_ACTOR
