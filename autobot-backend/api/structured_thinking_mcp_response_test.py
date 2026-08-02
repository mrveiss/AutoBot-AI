# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: POST /mcp/generate_summary dropped its payload.

response_model=DataResponse[StructuredThinkingSummaryData] validated the flat
{"success", "session_id", "message", "thought_count", ...} dict against the
envelope, discarding everything but `success`. The fix declares
response_model=StructuredThinkingSummaryData directly.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.structured_thinking_mcp as structured_thinking_mcp
from api.structured_thinking_mcp import router
from auth_middleware import check_admin_permission


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/structured-thinking")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return TestClient(app)


class TestGenerateSummaryMcpResponsePayload:
    def test_returns_the_real_session_message_on_the_wire(self):
        client = _make_client()
        structured_thinking_mcp.structured_sessions["empty-session"] = []

        try:
            response = client.post(
                "/api/structured-thinking/mcp/generate_summary",
                json={"session_id": "empty-session"},
            )
        finally:
            structured_thinking_mcp.structured_sessions.pop("empty-session", None)

        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == "empty-session"
        assert body["message"] == "No thoughts recorded in this session"
        assert body["thought_count"] == 0
        assert body["success"] is True
