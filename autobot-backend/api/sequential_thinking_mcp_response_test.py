# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: DELETE /sessions/{session_id} dropped its payload.

response_model=DataResponse[SequentialThinkingClearData] validated the flat
{"success", "session_id", "thoughts_cleared", "message"} dict against the
envelope, discarding everything but `success`. The fix declares
response_model=SequentialThinkingClearData directly.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.sequential_thinking_mcp as sequential_thinking_mcp
from api.sequential_thinking_mcp import router
from auth_middleware import check_admin_permission


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/sequential-thinking")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


class TestClearThinkingSessionResponsePayload:
    def test_returns_the_real_cleared_count_on_the_wire(self):
        client = _make_client()
        sequential_thinking_mcp.thinking_sessions["sess-1"] = [
            {"thought_number": 1},
            {"thought_number": 2},
            {"thought_number": 3},
        ]

        try:
            response = client.delete("/api/sequential-thinking/sessions/sess-1")
        finally:
            sequential_thinking_mcp.thinking_sessions.pop("sess-1", None)

        assert response.status_code == 200
        body = response.json()
        assert body["thoughts_cleared"] == 3
        assert body["session_id"] == "sess-1"
        assert body["success"] is True
