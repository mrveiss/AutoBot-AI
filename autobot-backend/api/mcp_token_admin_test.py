# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the MCP admin token management API (Issue #6453).

Covers:
- POST /api/mcp/tokens  — create token, scope validation
- GET  /api/mcp/tokens  — list tokens with masked secrets
- DELETE /api/mcp/tokens/{id} — revoke + 404 on second revoke
- Non-admin access is rejected (401/403)
- Redis-backed validation path in AutoBotMCPServer
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.mcp_token_admin import router

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/api")


# ---------------------------------------------------------------------------
# Redis mock helpers
# ---------------------------------------------------------------------------


def _make_redis_mock() -> AsyncMock:
    """Return a pipeline-capable async Redis mock."""
    redis = AsyncMock()
    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    pipe.set = AsyncMock()
    pipe.delete = AsyncMock()
    pipe.sadd = AsyncMock()
    pipe.srem = AsyncMock()
    pipe.execute = AsyncMock(return_value=[True, True, True])
    redis.pipeline = MagicMock(return_value=pipe)
    redis.smembers = AsyncMock(return_value=set())
    redis.get = AsyncMock(return_value=None)
    return redis


def _admin_user():
    return {"user_id": "u1", "role": "admin"}


# ---------------------------------------------------------------------------
# POST /api/mcp/tokens
# ---------------------------------------------------------------------------


def test_create_token_success():
    redis_mock = _make_redis_mock()
    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/mcp/tokens",
            json={"scopes": ["kb", "memory"], "label": "test-token"},
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "token_id" in data
    assert "token" in data
    assert "kb" in data["scopes"]
    assert "memory" in data["scopes"]
    # Token format: <secret>:<scopes>
    assert ":" in data["token"]
    secret_part, scopes_part = data["token"].split(":", 1)
    assert len(secret_part) == 64  # 32 bytes hex
    assert set(scopes_part.split(",")) == {"kb", "memory"}


def test_create_token_invalid_scope():
    redis_mock = _make_redis_mock()
    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/mcp/tokens",
            json={"scopes": ["kb", "invalid_scope"], "label": ""},
        )
    assert resp.status_code == 422


def test_create_token_empty_scopes():
    redis_mock = _make_redis_mock()
    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.post("/api/mcp/tokens", json={"scopes": [], "label": ""})
    assert resp.status_code == 422


def test_create_token_non_admin_rejected():
    non_admin = {"user_id": "u2", "role": "user"}
    with patch(
        "api.mcp_token_admin.get_auth_middleware",
        return_value=MagicMock(get_user_from_request=MagicMock(return_value=non_admin)),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/mcp/tokens",
            json={"scopes": ["kb"], "label": ""},
        )
    # raise_auth_error raises HTTPException 403 or similar
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /api/mcp/tokens
# ---------------------------------------------------------------------------


def test_list_tokens_empty():
    redis_mock = _make_redis_mock()
    redis_mock.smembers = AsyncMock(return_value=set())
    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.get("/api/mcp/tokens")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["tokens"] == []


def test_list_tokens_with_entries():
    import time

    secret = "a" * 64
    tid = "abc123"
    record = json.dumps(
        {
            "token_id": tid,
            "scopes": ["kb"],
            "label": "my-label",
            "created_at": time.time() - 100,
            "last_used": time.time() - 10,
        }
    )

    async def _fake_get(key):
        if "id:" in key:
            return secret.encode("utf-8")
        if "by_secret:" in key:
            return record.encode("utf-8")
        return None

    redis_mock = _make_redis_mock()
    redis_mock.smembers = AsyncMock(return_value={tid.encode("utf-8")})
    redis_mock.get = AsyncMock(side_effect=_fake_get)

    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.get("/api/mcp/tokens")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    token_rec = data["tokens"][0]
    assert token_rec["token_id"] == tid
    assert token_rec["masked_secret"] == "aaaa..."
    assert "kb" in token_rec["scopes"]
    assert token_rec["last_used"] is not None


# ---------------------------------------------------------------------------
# DELETE /api/mcp/tokens/{token_id}
# ---------------------------------------------------------------------------


def test_revoke_token_success():
    secret = "b" * 64
    tid = "def456"
    redis_mock = _make_redis_mock()
    redis_mock.get = AsyncMock(return_value=secret.encode("utf-8"))

    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.delete(f"/api/mcp/tokens/{tid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["revoked"] is True
    assert data["token_id"] == tid


def test_revoke_token_not_found():
    redis_mock = _make_redis_mock()
    redis_mock.get = AsyncMock(return_value=None)

    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(return_value=redis_mock)),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app)
        resp = client.delete("/api/mcp/tokens/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Redis unavailable → 503
# ---------------------------------------------------------------------------


def test_create_token_redis_unavailable():
    with (
        patch("api.mcp_token_admin._get_redis", new=AsyncMock(side_effect=Exception("503 test"))),
        patch(
            "api.mcp_token_admin.get_auth_middleware",
            return_value=MagicMock(get_user_from_request=MagicMock(return_value=_admin_user())),
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/mcp/tokens", json={"scopes": ["kb"], "label": ""})
    assert resp.status_code in (500, 503)


# ---------------------------------------------------------------------------
# AutoBotMCPServer Redis validation path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_server_validates_redis_token():
    """_validate_redis_token returns scopes for a valid Redis-backed token."""
    import time

    from mcp.autobot_server import AutoBotMCPServer

    secret = "c" * 64
    record = json.dumps(
        {
            "token_id": "tok1",
            "scopes": ["kb", "memory"],
            "label": "",
            "created_at": time.time(),
            "last_used": None,
        }
    )

    async def _fake_get(key):
        if f"by_secret:{secret}" in key:
            return record.encode("utf-8")
        return None

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=_fake_get)
    redis_mock.set = AsyncMock()

    server = AutoBotMCPServer()
    with patch("mcp.autobot_server.get_async_redis_client", new=AsyncMock(return_value=redis_mock)):
        scopes = await server._validate_redis_token(f"{secret}:kb,memory")

    assert scopes is not None
    assert set(scopes) == {"kb", "memory"}


@pytest.mark.asyncio
async def test_server_redis_token_updates_last_used():
    """_validate_redis_token writes last_used timestamp back to Redis."""
    import time

    from mcp.autobot_server import AutoBotMCPServer

    secret = "d" * 64
    record = json.dumps(
        {
            "token_id": "tok2",
            "scopes": ["agents"],
            "label": "",
            "created_at": time.time(),
            "last_used": None,
        }
    )

    async def _fake_get(key):
        if f"by_secret:{secret}" in key:
            return record.encode("utf-8")
        return None

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=_fake_get)
    redis_mock.set = AsyncMock()

    server = AutoBotMCPServer()
    with patch("mcp.autobot_server.get_async_redis_client", new=AsyncMock(return_value=redis_mock)):
        await server._validate_redis_token(f"{secret}:agents")

    redis_mock.set.assert_called_once()
    call_args = redis_mock.set.call_args
    key_arg = call_args[0][0]
    assert f"by_secret:{secret}" in key_arg
    written = json.loads(call_args[0][1])
    assert written["last_used"] is not None


@pytest.mark.asyncio
async def test_server_redis_token_missing_returns_none():
    """_validate_redis_token returns None when secret not in Redis."""
    from mcp.autobot_server import AutoBotMCPServer

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)

    server = AutoBotMCPServer()
    with patch("mcp.autobot_server.get_async_redis_client", new=AsyncMock(return_value=redis_mock)):
        scopes = await server._validate_redis_token("nosecret:kb")

    assert scopes is None


@pytest.mark.asyncio
async def test_handle_request_falls_back_to_redis_token():
    """handle_request accepts a Redis-backed token when static token fails."""
    import time

    from mcp.autobot_server import AutoBotMCPServer

    secret = "e" * 64
    record = json.dumps(
        {
            "token_id": "tok3",
            "scopes": ["kb"],
            "label": "",
            "created_at": time.time(),
            "last_used": None,
        }
    )

    async def _fake_get(key):
        if f"by_secret:{secret}" in key:
            return record.encode("utf-8")
        return None

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=_fake_get)
    redis_mock.set = AsyncMock()

    server = AutoBotMCPServer()
    with (
        patch("mcp.autobot_server.get_async_redis_client", new=AsyncMock(return_value=redis_mock)),
        patch.object(server, "_kb_list_categories", new=AsyncMock(return_value={"tree": []})),
    ):
        # Token is NOT in env var — static validation fails; Redis validation succeeds
        resp = await server.handle_request(
            "tools/call",
            {"name": "kb.list_categories", "arguments": {}},
            f"{secret}:kb",
        )

    assert "result" in resp, f"Expected result, got: {resp}"
