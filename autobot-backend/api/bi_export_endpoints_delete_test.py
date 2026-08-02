# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: DELETE /reports/saved/{id} dropped its payload.

response_model=DataResponse[SavedReportDeleteResponse] validated the flat
{"report_id", "deleted"} dict against the envelope and discarded both keys.
The fix declares response_model=SavedReportDeleteResponse directly.
"""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.bi_export_endpoints import router
from auth_middleware import check_admin_permission


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/bi")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


class TestDeleteSavedReportResponsePayload:
    def test_delete_returns_the_deleted_flag_and_report_id_on_the_wire(self):
        client = _make_client()
        mock_service = AsyncMock()
        mock_service.delete_report.return_value = True

        with patch(
            "api.bi_export_endpoints.get_saved_reports_service",
            return_value=mock_service,
        ):
            response = client.delete("/api/bi/reports/saved/report-42")

        assert response.status_code == 200
        body = response.json()
        assert body["report_id"] == "report-42"
        assert body["deleted"] is True
        mock_service.delete_report.assert_awaited_once_with("report-42")
