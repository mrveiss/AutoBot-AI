# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for MCPDispatcher's external-MCP-server integration (#11542, owner decision on #16458).

External tools merge into the same tool cache internal bridges populate,
each carrying Permission.MCP_EXTERNAL as required_permission — so the
canonical RBAC gate (_would_deny/dispatch) and BEFORE_TOOL_EXECUTE's
PermissionEnforcementExtension cover them exactly like a built-in tool.
Per-server allowed_roles is a second, narrower check MCPExternalBridge
applies on top, exercised in services/mcp_external_bridge_test.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp_dispatch import MCPDispatcher
from type_defs.mcp import MCPToolDefinition


def _make_tool(name: str) -> MCPToolDefinition:
    raw = {"name": name, "description": "An external tool", "inputSchema": {"type": "object", "properties": {}}}
    return MCPToolDefinition.model_validate(raw)


def _mock_registry_response(tools: list[dict]):
    resp = AsyncMock()
    resp.status = 200
    resp.json = AsyncMock(return_value={"tools": tools})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = AsyncMock(return_value=resp)
    return session


class TestMergeExternalTools:
    @pytest.mark.asyncio
    async def test_external_tool_merged_with_mcp_external_permission(self):
        d = MCPDispatcher()
        external_bridge = MagicMock()
        external_bridge.list_tools = AsyncMock(return_value=[_make_tool("fs_read")])

        with patch("services.mcp_dispatch.get_http_client", return_value=_mock_registry_response([])):
            with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
                await d.refresh_tool_cache()

        entry = d.find_tool("fs_read")
        assert entry is not None
        assert entry["bridge"] == "external"
        assert entry["required_permission"] == "mcp.external"

    @pytest.mark.asyncio
    async def test_internal_and_external_tools_coexist(self):
        d = MCPDispatcher()
        internal_tool = {
            "name": "search_knowledge_base",
            "description": "internal",
            "input_schema": {},
            "bridge": "knowledge_mcp",
            "endpoint": "http://x/search",
            "required_permission": "knowledge.read",
        }
        external_bridge = MagicMock()
        external_bridge.list_tools = AsyncMock(return_value=[_make_tool("fs_read")])

        with patch("services.mcp_dispatch.get_http_client", return_value=_mock_registry_response([internal_tool])):
            with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
                count = await d.refresh_tool_cache()

        assert count == 2
        assert d.find_tool("search_knowledge_base")["bridge"] == "knowledge_mcp"
        assert d.find_tool("fs_read")["bridge"] == "external"

    @pytest.mark.asyncio
    async def test_internal_tool_names_are_passed_as_reserved(self):
        """#16458 review: an external server must not be able to shadow a built-in
        tool's name. _merge_external_tools() must tell the bridge which names are
        already taken -- resolve_name_collisions_test.py proves the bridge honours
        reserved_names; this proves the caller actually supplies them.
        """
        d = MCPDispatcher()
        internal_tool = {
            "name": "search_knowledge_base",
            "description": "internal",
            "input_schema": {},
            "bridge": "knowledge_mcp",
            "endpoint": "http://x/search",
            "required_permission": "knowledge.read",
        }
        external_bridge = MagicMock()
        external_bridge.list_tools = AsyncMock(return_value=[])

        with patch("services.mcp_dispatch.get_http_client", return_value=_mock_registry_response([internal_tool])):
            with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
                await d.refresh_tool_cache()

        external_bridge.list_tools.assert_awaited_once_with(reserved_names=frozenset({"search_knowledge_base"}))

    @pytest.mark.asyncio
    async def test_external_tool_sharing_an_internal_name_never_overwrites_it(self):
        """End-to-end: even if a real bridge somehow still returned the bare
        name (a future bug in the bridge itself), the cache write for that
        name must not clobber the internal entry that already occupies it --
        defence in depth on top of the reserved_names contract above.
        """
        d = MCPDispatcher()
        internal_tool = {
            "name": "search_knowledge_base",
            "description": "internal",
            "input_schema": {},
            "bridge": "knowledge_mcp",
            "endpoint": "http://x/search",
            "required_permission": "knowledge.read",
        }
        # Simulates a bridge bug: returns the bare, un-prefixed internal name.
        external_bridge = MagicMock()
        external_bridge.list_tools = AsyncMock(return_value=[_make_tool("search_knowledge_base")])

        with patch("services.mcp_dispatch.get_http_client", return_value=_mock_registry_response([internal_tool])):
            with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
                await d.refresh_tool_cache()

        assert d.find_tool("search_knowledge_base")["bridge"] == "knowledge_mcp", (
            "an external tool sharing an internal tool's name overwrote it in the cache -- "
            "calls meant for the internal tool would silently route to the external server"
        )

    @pytest.mark.asyncio
    async def test_external_bridge_outage_does_not_block_internal_tools(self):
        d = MCPDispatcher()
        internal_tool = {
            "name": "search_knowledge_base",
            "description": "internal",
            "input_schema": {},
            "bridge": "knowledge_mcp",
            "endpoint": "http://x/search",
            "required_permission": "knowledge.read",
        }
        external_bridge = MagicMock()
        external_bridge.list_tools = AsyncMock(side_effect=RuntimeError("store down"))

        with patch("services.mcp_dispatch.get_http_client", return_value=_mock_registry_response([internal_tool])):
            with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
                count = await d.refresh_tool_cache()

        assert count == 1
        assert d.find_tool("search_knowledge_base") is not None
        assert d._cache_loaded is True

    @pytest.mark.asyncio
    async def test_internal_registry_failure_skips_external_merge_too(self):
        """Matches pre-#11542 contract: a registry-unreachable refresh stays cache_loaded=False."""
        import aiohttp

        d = MCPDispatcher()
        external_bridge = MagicMock()
        external_bridge.list_tools = AsyncMock(return_value=[_make_tool("fs_read")])

        with patch(
            "services.mcp_dispatch.get_http_client",
            side_effect=aiohttp.ClientConnectionError("refused"),
        ):
            with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
                count = await d.refresh_tool_cache()

        assert count == 0
        assert d._cache_loaded is False
        external_bridge.list_tools.assert_not_called()


class TestDispatchRoutesExternalTools:
    @pytest.mark.asyncio
    async def test_dispatch_denies_external_tool_without_mcp_external_permission(self):
        """A role without Permission.MCP_EXTERNAL is denied before ever reaching the bridge."""
        d = MCPDispatcher()
        d._cache_loaded = True
        d._tool_cache = {
            "fs_read": {
                "name": "fs_read",
                "description": "x",
                "input_schema": {},
                "bridge": "external",
                "endpoint": "",
                "required_permission": "mcp.external",
            }
        }

        result = await d.dispatch("fs_read", {}, role="readonly")

        assert result["success"] is False
        assert "denied" in result["result"].lower()

    @pytest.mark.asyncio
    async def test_dispatch_routes_permitted_external_tool_to_bridge(self):
        d = MCPDispatcher()
        d._cache_loaded = True
        d._tool_cache = {
            "fs_read": {
                "name": "fs_read",
                "description": "x",
                "input_schema": {},
                "bridge": "external",
                "endpoint": "",
                "required_permission": "mcp.external",
            }
        }

        from services.mcp_external_bridge import ExternalToolCallResult

        external_bridge = MagicMock()
        external_bridge.call_tool = AsyncMock(return_value=ExternalToolCallResult(success=True, result="ok"))

        with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
            result = await d.dispatch("fs_read", {}, role="admin")

        assert result["success"] is True
        assert result["bridge"] == "external"
        external_bridge.call_tool.assert_awaited_once_with("fs_read", {}, role="admin")

    @pytest.mark.asyncio
    async def test_dispatch_surfaces_external_bridge_denial_as_failure(self):
        """MCPExternalBridge's own allowed_roles refusal surfaces as an ordinary failure, not a crash."""
        d = MCPDispatcher()
        d._cache_loaded = True
        d._tool_cache = {
            "fs_read": {
                "name": "fs_read",
                "description": "x",
                "input_schema": {},
                "bridge": "external",
                "endpoint": "",
                "required_permission": "mcp.external",
            }
        }

        from services.mcp_external_bridge import ExternalToolCallResult

        external_bridge = MagicMock()
        external_bridge.call_tool = AsyncMock(
            return_value=ExternalToolCallResult(success=False, error="role 'admin' is not permitted to call 'fs_read'")
        )

        with patch("services.mcp_external_bridge.get_mcp_external_bridge", return_value=external_bridge):
            result = await d.dispatch("fs_read", {}, role="admin")

        assert result["success"] is False
        assert "not permitted" in result["result"]
