# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #13259: POST /audit/cleanup and GET /audit/operations
dropped their payloads.

Both declared response_model=DataResponse[XData] over a flat dict return; the
fix declares the concrete flat model directly. Field-value assertions are the
regression guard -- a bare status_code == 200 check would still pass against
the bug (the envelope defaults message/timestamp to None but the request
still succeeds).
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.audit import check_admin_permission, router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


class TestCleanupOldLogsResponsePayload:
    def test_cleanup_reports_the_actual_retention_window_on_the_wire(self):
        client = _make_client()
        mock_logger = AsyncMock()

        with patch("api.audit.get_audit_logger", return_value=mock_logger):
            response = client.post(
                "/api/audit/cleanup",
                json={"days_to_keep": 45, "confirm": True},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["days_retained"] == 45
        assert "45" in body["message"]
        assert body["success"] is True
        mock_logger.cleanup_old_logs.assert_awaited_once_with(days_to_keep=45)


class TestListOperationTypesResponsePayload:
    def test_list_operation_types_returns_the_real_categories_on_the_wire(self):
        client = _make_client()

        fake_operations = {
            "auth.login": "security",
            "auth.logout": "security",
            "file.export": "data",
        }
        with patch("services.audit_logger.OPERATION_CATEGORIES", fake_operations):
            response = client.get("/api/audit/operations")

        assert response.status_code == 200
        body = response.json()
        assert sorted(body["categories"]["security"]) == ["auth.login", "auth.logout"]
        assert body["categories"]["data"] == ["file.export"]
        assert body["total_operations"] == 3
