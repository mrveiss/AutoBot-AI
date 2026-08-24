# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: POST /startup/phase dropped its payload.

response_model=DataResponse[StartupPhaseUpdateData] validated the flat
{"success", "phase", "progress"} dict against the envelope, discarding
`phase` and `progress`. The fix declares response_model=StartupPhaseUpdateData
directly.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.startup import router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/startup")
    return TestClient(app)


class TestUpdateStartupPhaseResponsePayload:
    def test_returns_the_real_phase_and_progress_on_the_wire(self):
        client = _make_client()

        response = client.post(
            "/api/startup/phase",
            params={"phase": "loading_knowledge", "message": "Loading KB", "progress": 55},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["phase"] == "loading_knowledge"
        assert body["progress"] == 55
        assert body["success"] is True
