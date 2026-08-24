# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: POST /overseer/query/{session_id} dropped its
payload.

response_model=DataResponse[OverseerQueryData] validated the flat
{"success", "plan_id", "analysis", "steps", "message"} dict against the
envelope, discarding every field but `success`. The fix declares
response_model=OverseerQueryData directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.overseer_handlers import router
from auth_middleware import get_current_user


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/overseer")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "test-user", "role": "admin"}
    return TestClient(app)


class TestSubmitQueryResponsePayload:
    def test_returns_the_real_plan_on_the_wire(self):
        client = _make_client()

        fake_step = MagicMock()
        fake_step.step_number = 1
        fake_step.description = "check disk usage"
        fake_step.command = "df -h"

        fake_plan = MagicMock()
        fake_plan.plan_id = "plan-123"
        fake_plan.analysis = "Disk usage inspection requested"
        fake_plan.steps = [fake_step]

        mock_overseer = MagicMock()
        mock_overseer.analyze_query = AsyncMock(return_value=fake_plan)

        with patch("api.overseer_handlers.OverseerAgent", return_value=mock_overseer):
            response = client.post(
                "/api/overseer/query/session-abc",
                params={"query": "check disk usage"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["plan_id"] == "plan-123"
        assert body["analysis"] == "Disk usage inspection requested"
        assert body["steps"][0]["command"] == "df -h"
        assert body["success"] is True
