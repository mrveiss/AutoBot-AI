# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`/sync` and `/hardware-priority` record the real actor, not "admin" (#16541).

#16504 wired both routes onto `require_settings_admin`, the same dependency
`settings_config_test.py::TestAnAdmittedWriteRecordsItsAuthor` already proves
for `POST /`. Neither route had its own test pinning the recorded actor --
only the shared dependency was covered, through a different route. Mirrors
that file's pattern: force the internal-service-key branch via
`verify_internal_api_key`, and read back what `create_revision` was actually
called with.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import settings_config
from api.settings import router
from api.user_management.dependencies import get_db_session


async def _fake_session():
    yield MagicMock()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/settings")
    app.dependency_overrides[get_db_session] = _fake_session
    return TestClient(app)


class TestSyncRecordsItsAuthor:
    @staticmethod
    def _recorded_author(*, internal_key: bool) -> str:
        revisions = MagicMock()
        revisions.return_value.create_revision = AsyncMock()

        with (
            patch("api.settings.ConfigService.get_full_config", return_value={}),
            patch("api.settings.ConfigService.clear_cache"),
            patch("api.settings.ConfigRevisionService", revisions),
            patch("api.settings._atomic_write_json", AsyncMock()),
            patch.object(settings_config, "verify_internal_api_key", return_value=internal_key),
        ):
            response = _client().post("/api/settings/sync", json={"settings": {"hardware": {}}})
        assert response.status_code == 200, response.text
        return revisions.return_value.create_revision.await_args.kwargs["created_by"]

    def test_an_admin_session_is_recorded_by_username(self):
        assert self._recorded_author(internal_key=False) == "test-user"

    def test_the_internal_service_key_is_recorded_as_the_service(self):
        assert self._recorded_author(internal_key=True) == settings_config.INTERNAL_SERVICE_ACTOR


class TestHardwarePriorityRecordsItsAuthor:
    @staticmethod
    def _recorded_author(*, internal_key: bool) -> str:
        from hardware_acceleration import AccelerationType

        mock_hw = MagicMock()
        mock_hw.update_priorities = MagicMock()
        mock_hw.current_config = {"priority_order": [AccelerationType.NPU, AccelerationType.GPU, AccelerationType.CPU]}
        revisions = MagicMock()
        revisions.return_value.create_revision = AsyncMock()

        with (
            patch("api.settings.ConfigService.get_full_config", return_value={"hardware": {"acceleration": {}}}),
            patch("api.settings.ConfigService.save_full_config", return_value={"status": "ok"}),
            patch("api.settings.ConfigRevisionService", revisions),
            patch("hardware_acceleration.get_hardware_acceleration_manager", return_value=mock_hw),
            patch.object(settings_config, "verify_internal_api_key", return_value=internal_key),
        ):
            response = _client().patch(
                "/api/settings/hardware-priority",
                json={"priority_order": ["npu", "gpu", "cpu"]},
            )
        assert response.status_code == 200, response.text
        return revisions.return_value.create_revision.await_args.kwargs["created_by"]

    def test_an_admin_session_is_recorded_by_username(self):
        assert self._recorded_author(internal_key=False) == "test-user"

    def test_the_internal_service_key_is_recorded_as_the_service(self):
        assert self._recorded_author(internal_key=True) == settings_config.INTERNAL_SERVICE_ACTOR
