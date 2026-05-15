# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the FastAPI MCP router HTTP status-code mapping.

Covers the translation of JSON-RPC error codes to HTTP status codes so that
HTTP clients receive proper 4xx responses instead of opaque 200 OK payloads.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.autobot_mcp_router import router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/api")

client = TestClient(app)


def _json_rpc_body(method: str = "tools/call", name: str = "kb.search") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {"name": name, "arguments": {}},
    }


def _mock_response(error_code: int, message: str = "error") -> dict:
    return {"jsonrpc": "2.0", "id": 1, "error": {"code": error_code, "message": message}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_code, expected_status",
    [
        (-32001, 401),  # invalid / expired token
        (-32003, 403),  # scope denied — regression guard for GH#7659
        (-32029, 429),  # rate limited
        (-32000, 200),  # generic server error — stays 200
        (-32602, 200),  # invalid params — stays 200
    ],
)
def test_error_code_maps_to_correct_http_status(error_code: int, expected_status: int) -> None:
    mock_resp = _mock_response(error_code)
    with patch("api.autobot_mcp_router.AutoBotMCPServer") as mock_cls:
        instance = mock_cls.return_value
        instance.handle_request = AsyncMock(return_value=mock_resp)
        response = client.post(
            "/api/mcp/tool",
            json=_json_rpc_body(),
            headers={"Authorization": "Bearer test-token"},
        )
    assert (
        response.status_code == expected_status
    ), f"error code {error_code} should map to HTTP {expected_status}, got {response.status_code}"


def test_successful_tool_call_returns_200() -> None:
    mock_resp = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "ok"}]}}
    with patch("api.autobot_mcp_router.AutoBotMCPServer") as mock_cls:
        instance = mock_cls.return_value
        instance.handle_request = AsyncMock(return_value=mock_resp)
        response = client.post(
            "/api/mcp/tool",
            json=_json_rpc_body(),
            headers={"Authorization": "Bearer valid-token"},
        )
    assert response.status_code == 200
    assert response.json()["result"]["content"][0]["text"] == "ok"


def test_malformed_json_returns_400() -> None:
    response = client.post(
        "/api/mcp/tool",
        content=b"not json",
        headers={"Authorization": "Bearer token", "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == -32700
