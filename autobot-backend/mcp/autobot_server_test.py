# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AutoBotMCPServer (Issue #5072).

Covers:
- tools/list returns tool manifest for valid token
- kb.list_categories delegates to KB and returns result
- Rate limiting rejects the 51st request in the same window
- Unknown tool returns JSON-RPC error -32602
- Invalid / missing token returns JSON-RPC error -32001
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.ssot_config import config
from mcp.autobot_server import AutoBotMCPServer, _stdio_bearer_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# #13263: these tests configure their own secret rather than relying on a
# shipped default. AUTOBOT_MCP_TOKEN now defaults to "" (unconfigured, fails
# closed) because any non-empty default is itself a working credential.
TEST_SECRET = "test-mcp-secret"
VALID_TOKEN = f"{TEST_SECRET}:kb,memory,agents"
KB_TOKEN = f"{TEST_SECRET}:kb"


@pytest.fixture(autouse=True)
def _configure_mcp_secret():
    """Give every test in this module a configured secret to authenticate against."""
    with patch.object(config.misc, "mcp_token", TEST_SECRET):
        yield


def make_server() -> AutoBotMCPServer:
    return AutoBotMCPServer()


# ---------------------------------------------------------------------------
# initialize / tools/list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tools_list_returns_manifest():
    server = make_server()
    resp = await server.handle_request("tools/list", {}, VALID_TOKEN, req_id=1)
    assert resp["id"] == 1
    assert "result" in resp
    result = resp["result"]
    assert result["serverInfo"]["name"] == "autobot-mcp"
    tool_names = {t["name"] for t in result["tools"]}
    assert "kb.search" in tool_names
    assert "memory.entity_lookup" in tool_names
    assert "agents.list" in tool_names


@pytest.mark.asyncio
async def test_initialize_alias():
    server = make_server()
    resp = await server.handle_request("initialize", {}, VALID_TOKEN)
    assert "result" in resp


@pytest.mark.asyncio
async def test_scoped_token_restricts_tools():
    server = make_server()
    resp = await server.handle_request("tools/list", {}, KB_TOKEN)
    tool_names = {t["name"] for t in resp["result"]["tools"]}
    assert all(n.startswith("kb.") for n in tool_names)
    assert "memory.entity_lookup" not in tool_names


# ---------------------------------------------------------------------------
# kb.list_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kb_list_categories():
    server = make_server()
    fake_kb = AsyncMock()
    fake_kb.get_category_tree = AsyncMock(return_value={"tree": [{"id": "cat1", "name": "General"}]})

    with patch(
        "mcp.autobot_server.AutoBotMCPServer._kb_list_categories",
        new=AsyncMock(return_value={"tree": [{"id": "cat1", "name": "General"}]}),
    ):
        resp = await server.handle_request(
            "tools/call",
            {"name": "kb.list_categories", "arguments": {}},
            KB_TOKEN,
        )

    assert "result" in resp
    import json

    content = json.loads(resp["result"]["content"][0]["text"])
    assert "tree" in content


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_after_50_requests():
    server = make_server()
    # Exhaust the 50-request window
    for _ in range(50):
        r = await server.handle_request("tools/list", {}, VALID_TOKEN)
        assert "result" in r, "should succeed within limit"

    # 51st request should be rate-limited
    r = await server.handle_request("tools/list", {}, VALID_TOKEN)
    assert "error" in r
    assert r["error"]["code"] == -32029


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_returns_error():
    server = make_server()
    resp = await server.handle_request(
        "tools/call",
        {"name": "kb.does_not_exist", "arguments": {}},
        KB_TOKEN,
    )
    assert "error" in resp
    assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_token_returns_401():
    server = make_server()
    resp = await server.handle_request("tools/list", {}, "")
    assert "error" in resp
    assert resp["error"]["code"] == -32001


@pytest.mark.asyncio
async def test_wrong_secret_returns_401():
    server = make_server()
    resp = await server.handle_request("tools/list", {}, "wrongsecret:kb,memory,agents")
    assert "error" in resp
    assert resp["error"]["code"] == -32001


def test_empty_secret_rejected_with_configured_secret():
    """#13263: ``":<scopes>"`` carries no secret and must never authenticate."""
    assert AutoBotMCPServer._validate_token(":kb,memory,agents") is None


def test_empty_secret_rejected_when_configured_secret_is_blank():
    """#13263: the check fails closed even when AUTOBOT_MCP_TOKEN is blank.

    Before the fix ``expected`` was ``""`` by default, so ``secret_part != expected``
    was False for a token beginning with ``:`` — the caller was authenticated and
    granted exactly the scopes it named for itself.
    """
    with patch.object(config.misc, "mcp_token", ""):
        assert AutoBotMCPServer._validate_token(":kb,memory,agents") is None
        assert AutoBotMCPServer._validate_token(":") is None
        assert AutoBotMCPServer._validate_token("dev:kb,memory,agents") is None


@pytest.mark.asyncio
async def test_empty_secret_token_returns_401_end_to_end():
    """#13263: the empty-secret token is rejected through the full request path."""
    server = make_server()
    with (
        patch.object(config.misc, "mcp_token", ""),
        patch.object(AutoBotMCPServer, "_validate_redis_token", new=AsyncMock(return_value=None)),
    ):
        resp = await server.handle_request("tools/list", {}, ":kb,memory,agents")
    assert "error" in resp
    assert resp["error"]["code"] == -32001


@pytest.mark.asyncio
async def test_scope_denied_for_tool():
    """KB-only token cannot call agents.list."""
    server = make_server()
    resp = await server.handle_request(
        "tools/call",
        {"name": "agents.list", "arguments": {}},
        KB_TOKEN,
    )
    assert "error" in resp
    assert resp["error"]["code"] == -32001


# ---------------------------------------------------------------------------
# agents.list (no external deps)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agents_list_returns_registry():
    server = make_server()
    resp = await server.handle_request(
        "tools/call",
        {"name": "agents.list", "arguments": {}},
        VALID_TOKEN,
    )
    assert "result" in resp
    import json

    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["count"] > 0
    ids = [a["id"] for a in content["agents"]]
    assert "chat_agent" in ids


# ---------------------------------------------------------------------------
# Unknown method
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_method_returns_error():
    server = make_server()
    resp = await server.handle_request("unknown/method", {}, VALID_TOKEN)
    assert "error" in resp
    assert resp["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# Run JWT auth (SEC-2 Phase 2, #6473)
# ---------------------------------------------------------------------------

_FAKE_KB_CLAIMS = {
    "jti": "test-jti",
    "run_id": "r1",
    "task_id": "t1",
    "agent_id": "a1",
    "tenant_id": "x",
    "scope": ["mcp:knowledge"],
}
_FAKE_AGENT_CLAIMS = {
    "jti": "test-jti2",
    "run_id": "r2",
    "task_id": "t2",
    "agent_id": "a2",
    "tenant_id": "x",
    "scope": ["agent:invoke"],
}


@pytest.mark.asyncio
async def test_run_jwt_correct_scope_passes():
    """Agent with mcp:knowledge JWT can call kb.* tools."""
    server = make_server()
    with patch("mcp.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_FAKE_KB_CLAIMS)):
        with patch.object(server, "_kb_list_categories", new=AsyncMock(return_value={"tree": []})):
            resp = await server.handle_request(
                "tools/call",
                {"name": "kb.list_categories", "arguments": {}, "run_jwt": "fake.jwt.token"},
                "",
            )
    assert "result" in resp, f"Expected result, got: {resp}"


@pytest.mark.asyncio
async def test_run_jwt_insufficient_scope_returns_403():
    """Agent with mcp:knowledge JWT cannot call agents.* tools — returns -32003."""
    server = make_server()
    with patch("mcp.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_FAKE_KB_CLAIMS)):
        resp = await server.handle_request(
            "tools/call",
            {"name": "agents.list", "arguments": {}, "run_jwt": "fake.jwt.token"},
            "",
        )
    assert "error" in resp
    assert resp["error"]["code"] == -32003
    assert "Forbidden" in resp["error"]["message"]


@pytest.mark.asyncio
async def test_run_jwt_invalid_token_returns_401():
    """Malformed or expired run JWT returns -32001 (401)."""
    from autobot_shared.auth.jwt_core import JWTDecodeError

    server = make_server()
    with patch("mcp.autobot_server.validate_run_jwt", new=AsyncMock(side_effect=JWTDecodeError("bad sig"))):
        resp = await server.handle_request(
            "tools/call",
            {"name": "kb.list_categories", "arguments": {}, "run_jwt": "invalid.token.value"},
            "",
        )
    assert "error" in resp
    assert resp["error"]["code"] == -32001


@pytest.mark.asyncio
async def test_run_jwt_agent_invoke_scope_grants_agents_tools():
    """Agent with agent:invoke JWT can call agents.list."""
    server = make_server()
    with patch("mcp.autobot_server.validate_run_jwt", new=AsyncMock(return_value=_FAKE_AGENT_CLAIMS)):
        resp = await server.handle_request(
            "tools/call",
            {"name": "agents.list", "arguments": {}, "run_jwt": "fake.jwt.token2"},
            "",
        )
    assert "result" in resp, f"Expected result, got: {resp}"


@pytest.mark.asyncio
async def test_legacy_token_still_works_without_run_jwt():
    """Direct user-driven calls using AUTOBOT_MCP_TOKEN still pass (backward compat)."""
    server = make_server()
    resp = await server.handle_request("tools/list", {}, VALID_TOKEN)
    assert "result" in resp
    tool_names = {t["name"] for t in resp["result"]["tools"]}
    assert "kb.search" in tool_names


# ---------------------------------------------------------------------------
# #13266: AUTOBOT_MCP_TOKEN has exactly one meaning (the secret segment)
# ---------------------------------------------------------------------------


def test_stdio_bearer_is_composed_from_secret_plus_scopes():
    """#13266: stdio composes "<secret>:<scopes>" instead of reusing the secret as a bearer."""
    with patch.object(config.misc, "mcp_token", TEST_SECRET), patch.object(
        config.misc, "mcp_stdio_scopes", "kb,memory"
    ):
        assert _stdio_bearer_token() == f"{TEST_SECRET}:kb,memory"


@pytest.mark.asyncio
async def test_stdio_bearer_authenticates_end_to_end():
    """#13266: the token stdio presents is accepted by the validator it is checked against.

    Before the fix no value of AUTOBOT_MCP_TOKEN satisfied both readings, so
    every stdio request was rejected with -32001 in every configuration.
    """
    server = make_server()
    with patch.object(config.misc, "mcp_token", TEST_SECRET), patch.object(
        config.misc, "mcp_stdio_scopes", "kb,memory,agents"
    ):
        resp = await server.handle_request("tools/list", {}, _stdio_bearer_token(), req_id=7, client_ip="stdio")

    assert "error" not in resp, resp
    assert {t["name"] for t in resp["result"]["tools"]} & {"kb.search"}


def test_stdio_refuses_to_run_without_a_configured_secret():
    """#13266/#13263: no default credential — an unset secret is fatal, not permissive."""
    with patch.object(config.misc, "mcp_token", ""):
        with pytest.raises(RuntimeError, match="AUTOBOT_MCP_TOKEN"):
            _stdio_bearer_token()


def test_stdio_refuses_to_run_with_no_scopes():
    """An empty scope list would compose a token that grants nothing; fail loudly instead."""
    with patch.object(config.misc, "mcp_token", TEST_SECRET), patch.object(config.misc, "mcp_stdio_scopes", " , "):
        with pytest.raises(RuntimeError, match="scopes"):
            _stdio_bearer_token()


def test_stdio_rejects_the_overloaded_full_token_form():
    """#13266: a '<secret>:<scopes>' value in AUTOBOT_MCP_TOKEN is named, not silently broken."""
    with patch.object(config.misc, "mcp_token", f"{TEST_SECRET}:kb,memory,agents"):
        with pytest.raises(RuntimeError, match="SECRET SEGMENT ONLY"):
            _stdio_bearer_token()
