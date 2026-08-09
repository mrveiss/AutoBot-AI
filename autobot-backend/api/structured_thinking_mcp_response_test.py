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
        """Empty-session branch: the 4-key early return at :363-369."""
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

    def test_returns_the_real_summary_fields_for_a_populated_session_on_the_wire(self):
        """Populated-session branch: the 6-key summary at :376-403.

        stage_progression is a Dict[str, List[...]] keyed by stage (built by
        _build_stage_progression), not a List -- and cognitive_flow must be
        declared on the model at all, or FastAPI drops it silently even after
        the DataResponse envelope fix (#13259 review: the empty-session case
        above never reaches this branch and would not have caught either
        defect).
        """
        client = _make_client()
        structured_thinking_mcp.structured_sessions["populated-session"] = [
            {
                "thought_number": 1,
                "thought": "first thought",
                "total_thoughts": 1,
                "next_thought_needed": False,
                "stage": "Analysis",
                "tags": ["scope"],
                "axioms_used": ["axiom-a"],
                "assumptions_challenged": ["assumption-a"],
                "timestamp": "2026-08-03T00:00:00+00:00",
            }
        ]

        try:
            response = client.post(
                "/api/structured-thinking/mcp/generate_summary",
                json={"session_id": "populated-session"},
            )
        finally:
            structured_thinking_mcp.structured_sessions.pop("populated-session", None)

        assert response.status_code == 200
        body = response.json()
        assert body["overview"]["total_thoughts"] == 1
        assert body["stage_progression"]["Analysis"][0]["thought_number"] == 1
        assert body["cognitive_flow"][0]["thought_number"] == 1
        assert body["cognitive_flow"][0]["stage"] == "Analysis"
