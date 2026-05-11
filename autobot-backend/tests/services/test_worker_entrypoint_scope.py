# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for per-call scope enforcement in worker_entrypoint (MVA-94).

Tests that _handle_request() checks TOOL_REQUIRED_SCOPE against the token
scope claim and returns -32001 / "insufficient scope" on mismatch.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.mcp_bridge_workers.worker_entrypoint as we
from services.mcp_bridge_workers.worker_entrypoint import (
    TOOL_REQUIRED_SCOPE,
    _handle_request,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BRIDGE = MagicMock()


def _req(tool: str, arguments: Optional[Dict[str, Any]] = None, run_jwt: str = "tok") -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "call",
        "params": {"tool": tool, "arguments": arguments or {}, "run_jwt": run_jwt},
    }


def _claims(scopes: list) -> Dict[str, Any]:
    return {"scope": scopes, "run_id": "r1", "agent_id": "a1", "tenant_id": "t1"}


# ---------------------------------------------------------------------------
# Scope mismatch tests
# ---------------------------------------------------------------------------


class TestScopeMismatch:
    """_handle_request returns -32001 / 'insufficient scope' on scope mismatch."""

    @pytest.mark.asyncio
    async def test_filesystem_tool_with_wrong_scope_returns_insufficient_scope(self):
        """read_text_file requires mcp:filesystem; task:read is insufficient."""
        claims = _claims(["task:read"])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            resp = await _handle_request(_BRIDGE, _req("read_text_file"))

        assert resp["error"]["code"] == -32001
        assert "insufficient scope" in resp["error"]["message"]
        assert "mcp:filesystem" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_knowledge_tool_with_wrong_scope_returns_insufficient_scope(self):
        """search_knowledge_base requires mcp:knowledge; mcp:filesystem is insufficient."""
        claims = _claims(["mcp:filesystem"])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            resp = await _handle_request(_BRIDGE, _req("search_knowledge_base"))

        assert resp["error"]["code"] == -32001
        assert "mcp:knowledge" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_web_fetch_tool_with_wrong_scope_returns_insufficient_scope(self):
        """scrape_url requires mcp:web_fetch; mcp:knowledge is insufficient."""
        claims = _claims(["mcp:knowledge"])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            resp = await _handle_request(_BRIDGE, _req("scrape_url"))

        assert resp["error"]["code"] == -32001
        assert "mcp:web_fetch" in resp["error"]["message"]

    @pytest.mark.asyncio
    async def test_empty_scope_list_returns_insufficient_scope(self):
        """A token with no scopes is rejected for any mapped tool."""
        claims = _claims([])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            resp = await _handle_request(_BRIDGE, _req("write_file"))

        assert resp["error"]["code"] == -32001

    @pytest.mark.asyncio
    async def test_error_has_no_result_field(self):
        """Scope-mismatch response must not include a 'result' key."""
        claims = _claims(["task:read"])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            resp = await _handle_request(_BRIDGE, _req("list_directory"))

        assert "result" not in resp


# ---------------------------------------------------------------------------
# Matching scope passes through
# ---------------------------------------------------------------------------


class TestScopeMatch:
    """_handle_request dispatches to the bridge when scope covers the tool."""

    @pytest.mark.asyncio
    async def test_filesystem_tool_with_filesystem_scope_passes_through(self):
        """read_text_file with mcp:filesystem scope reaches _invoke_tool."""
        claims = _claims(["mcp:filesystem"])
        tool_result = {"content": "hello"}
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            with patch.object(we, "_invoke_tool", AsyncMock(return_value=tool_result)) as mock_invoke:
                resp = await _handle_request(_BRIDGE, _req("read_text_file"))

        mock_invoke.assert_awaited_once()
        assert resp["result"] == tool_result

    @pytest.mark.asyncio
    async def test_knowledge_tool_with_knowledge_scope_passes_through(self):
        """search_knowledge_base with mcp:knowledge scope reaches _invoke_tool."""
        claims = _claims(["mcp:knowledge"])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            with patch.object(we, "_invoke_tool", AsyncMock(return_value={"hits": []})) as mock_invoke:
                resp = await _handle_request(_BRIDGE, _req("search_knowledge_base"))

        mock_invoke.assert_awaited_once()
        assert "error" not in resp

    @pytest.mark.asyncio
    async def test_multi_scope_token_satisfies_required_scope(self):
        """A token with multiple scopes passes when it includes the required one."""
        claims = _claims(["task:read", "mcp:web_fetch", "mcp:filesystem"])
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            with patch.object(we, "_invoke_tool", AsyncMock(return_value={})) as mock_invoke:
                resp = await _handle_request(_BRIDGE, _req("scrape_url"))

        mock_invoke.assert_awaited_once()
        assert "error" not in resp

    @pytest.mark.asyncio
    async def test_unknown_tool_not_in_mapping_passes_through(self):
        """A tool not in TOOL_REQUIRED_SCOPE is allowed regardless of scope."""
        assert "unknown_tool" not in TOOL_REQUIRED_SCOPE
        claims = _claims([])  # no scopes at all
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=claims)):
            with patch.object(we, "_invoke_tool", AsyncMock(return_value={"ok": True})) as mock_invoke:
                resp = await _handle_request(_BRIDGE, _req("unknown_tool"))

        mock_invoke.assert_awaited_once()
        assert "error" not in resp

    @pytest.mark.asyncio
    async def test_jwt_enforcement_off_skips_scope_check(self):
        """When JWT enforcement is off, _validate_run_jwt_param returns None
        and no scope check is performed."""
        with patch.object(we, "_validate_run_jwt_param", AsyncMock(return_value=None)):
            with patch.object(we, "_invoke_tool", AsyncMock(return_value={})) as mock_invoke:
                resp = await _handle_request(_BRIDGE, _req("read_text_file"))

        mock_invoke.assert_awaited_once()
        assert "error" not in resp


# ---------------------------------------------------------------------------
# TOOL_REQUIRED_SCOPE sanity checks
# ---------------------------------------------------------------------------


class TestToolRequiredScopeMapping:
    """Basic structural checks on the TOOL_REQUIRED_SCOPE constant."""

    def test_all_values_are_valid_scopes(self):
        """Every scope in the mapping is one of the known VALID_SCOPES strings."""
        # We only import VALID_SCOPES to validate without coupling to run_jwt.
        valid = {"mcp:knowledge", "mcp:web_fetch", "mcp:filesystem", "task:read", "task:write", "agent:invoke"}
        for tool, scope in TOOL_REQUIRED_SCOPE.items():
            assert scope in valid, f"Unknown scope {scope!r} for tool {tool!r}"

    def test_filesystem_tools_have_filesystem_scope(self):
        assert TOOL_REQUIRED_SCOPE["read_text_file"] == "mcp:filesystem"
        assert TOOL_REQUIRED_SCOPE["write_file"] == "mcp:filesystem"
        assert TOOL_REQUIRED_SCOPE["list_directory"] == "mcp:filesystem"

    def test_knowledge_tools_have_knowledge_scope(self):
        assert TOOL_REQUIRED_SCOPE["search_knowledge_base"] == "mcp:knowledge"
        assert TOOL_REQUIRED_SCOPE["add_to_knowledge_base"] == "mcp:knowledge"

    def test_web_fetch_tools_have_web_fetch_scope(self):
        assert TOOL_REQUIRED_SCOPE["scrape_url"] == "mcp:web_fetch"
        assert TOOL_REQUIRED_SCOPE["crawl_site"] == "mcp:web_fetch"
        assert TOOL_REQUIRED_SCOPE["get"] == "mcp:web_fetch"
