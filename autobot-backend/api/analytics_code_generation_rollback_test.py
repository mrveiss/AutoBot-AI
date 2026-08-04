# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: POST /code-generation/rollback dropped its payload.

response_model=DataResponse[AnalyticsCodeGenRollbackData] validated the flat
{"success", "file_path", "version_id", "code"} dict against the
{success, data, message, timestamp} envelope, discarding every field but
`success`. The fix declares response_model=AnalyticsCodeGenRollbackData
directly. A status_code == 200 assertion alone would have passed against the
bug (`data` was still null with a 200); the field-value assertions below are
the actual regression guard.
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.analytics_code_generation import router
from auth_middleware import check_admin_permission


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/code-generation")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


class TestRollbackCodeResponsePayload:
    def test_rollback_code_returns_the_restored_source_on_the_wire(self):
        client = _make_client()
        mock_engine = AsyncMock()
        mock_engine.rollback.return_value = "print('restored version')"

        with patch(
            "api.analytics_code_generation.get_code_generation_engine",
            return_value=mock_engine,
        ):
            response = client.post(
                "/api/code-generation/rollback",
                json={"file_path": "app/main.py", "version_id": "v3"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["code"] == "print('restored version')"
        assert body["file_path"] == "app/main.py"
        assert body["version_id"] == "v3"
        assert body["success"] is True
