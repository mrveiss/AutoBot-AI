# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pytest suite for RealtimeMCPBridge (Issue #7343).

Covers:
 1. Schema translation (object/array/primitive/missing-schema)
 2. Name-collision resolution across servers
 3. Successful tool call routing
 4. Tool call error (MCPError) surfaced as is_error=True
 5. Transport-down (connection failure) handled gracefully
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.realtime_mcp_bridge import (
    RealtimeMCPBridge,
    _server_id_from_uri,
    _translate_input_schema,
    _translate_property,
)
from type_defs.mcp import MCPInputSchema, MCPPropertyDefinition, MCPToolDefinition


class MCPError(Exception):
    """Minimal MCPError stand-in for tests (avoids importing skills package)."""

    def __init__(self, code: int = -1, message: str = "error", data=None):
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.data = data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, description: str = "A tool", schema: dict | None = None) -> MCPToolDefinition:
    """Build a minimal MCPToolDefinition for tests."""
    if schema is None:
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "query"}},
            "required": ["q"],
        }
    raw = {"name": name, "description": description, "inputSchema": schema}
    return MCPToolDefinition.model_validate(raw)


def _make_bridge(server_uris: list[str] | None = None, is_admin: bool = False) -> RealtimeMCPBridge:
    """Return a bridge with optional server URIs and mocked bundle filtering."""
    bridge = RealtimeMCPBridge(is_admin=is_admin, server_uris=server_uris or [])
    return bridge


# ---------------------------------------------------------------------------
# 1. Schema translation
# ---------------------------------------------------------------------------


class TestTranslateProperty:
    """Unit tests for _translate_property."""

    def test_primitive_string(self):
        result = _translate_property({"type": "string", "description": "A string"})
        assert result == {"type": "string", "description": "A string"}

    def test_primitive_integer(self):
        result = _translate_property({"type": "integer", "default": 10})
        assert result["type"] == "integer"
        assert result["default"] == 10

    def test_enum(self):
        result = _translate_property({"type": "string", "enum": ["a", "b"]})
        assert result["enum"] == ["a", "b"]

    def test_array_with_items(self):
        prop = {"type": "array", "items": {"type": "string"}}
        result = _translate_property(prop)
        assert result["type"] == "array"
        assert result["items"] == {"type": "string"}

    def test_nested_object(self):
        prop = {
            "type": "object",
            "properties": {"inner": {"type": "integer", "description": "inner field"}},
            "required": ["inner"],
        }
        result = _translate_property(prop)
        assert result["type"] == "object"
        assert "inner" in result["properties"]
        assert result["required"] == ["inner"]

    def test_none_returns_empty(self):
        assert _translate_property(None) == {}

    def test_pydantic_model(self):
        prop = MCPPropertyDefinition(type="boolean", description="flag")
        result = _translate_property(prop)
        assert result["type"] == "boolean"
        assert result["description"] == "flag"


class TestTranslateInputSchema:
    """Unit tests for _translate_input_schema."""

    def test_none_returns_fallback(self):
        result = _translate_input_schema(None)
        assert result["type"] == "object"
        assert result["additionalProperties"] is True

    def test_empty_dict_returns_fallback(self):
        result = _translate_input_schema({})
        assert result["type"] == "object"
        assert result["additionalProperties"] is True

    def test_basic_object_schema(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        }
        result = _translate_input_schema(schema)
        assert result["type"] == "object"
        assert "name" in result["properties"]
        assert result["required"] == ["name"]
        assert result["additionalProperties"] is False

    def test_additionalproperties_defaults_false(self):
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }
        result = _translate_input_schema(schema)
        assert result["additionalProperties"] is False

    def test_missing_schema_on_tool_falls_back(self):
        """A tool with no inputSchema gets the fallback parameters dict."""
        tool_raw = {
            "name": "no_schema_tool",
            "description": "no schema",
            "inputSchema": {},
        }
        tool = MCPToolDefinition.model_validate(tool_raw)
        result = _translate_input_schema(tool.input_schema)
        # MCPInputSchema with empty properties → default schema with type=object
        assert result["type"] == "object"

    def test_pydantic_mcp_input_schema(self):
        schema = MCPInputSchema(
            properties={"path": MCPPropertyDefinition(type="string", description="file path")},
            required=["path"],
        )
        result = _translate_input_schema(schema)
        assert result["type"] == "object"
        assert "path" in result["properties"]
        assert result["required"] == ["path"]


# ---------------------------------------------------------------------------
# 2. Server-ID helper
# ---------------------------------------------------------------------------


class TestServerIdFromUri:
    def test_http_uri(self):
        assert _server_id_from_uri("http://localhost:8200") == "localhost_8200"

    def test_sse_uri(self):
        assert _server_id_from_uri("sse://mcp.example.com/events") == "mcp_example_com"

    def test_stdio_uri(self):
        sid = _server_id_from_uri("stdio://npx -y server")
        assert sid.startswith("npx")

    def test_empty_fallback(self):
        assert _server_id_from_uri("://") == "mcp"


# ---------------------------------------------------------------------------
# 3. Name-collision resolution
# ---------------------------------------------------------------------------


class TestNameCollisionResolution:
    """Verify that tools with the same name across servers get prefixed."""

    @pytest.mark.asyncio
    async def test_no_collision_keeps_bare_name(self):
        """Single server: tool keeps its original name."""
        tool = _make_tool("search")
        bridge = _make_bridge(server_uris=["http://server-a:8200"])

        mock_client = AsyncMock()
        mock_client.discover_tools = AsyncMock(return_value=[tool])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=lambda uri: mock_client,
        ):
            with patch(
                "services.realtime_mcp_bridge._get_filter_tools_for_bundle",
                return_value=lambda tools, **_: tools,
            ):
                result = await bridge.list_realtime_tools()

        names = [t.name for t in result]
        assert "search" in names
        assert all("__" not in n for n in names)

    @pytest.mark.asyncio
    async def test_collision_prefixes_both(self):
        """Two servers with the same tool name → both get prefixed."""
        tool_a = _make_tool("search")
        tool_b = _make_tool("search")

        uris = ["http://server-a:8200", "http://server-b:8200"]
        bridge = _make_bridge(server_uris=uris)

        # server-a client
        client_a = AsyncMock()
        client_a.discover_tools = AsyncMock(return_value=[tool_a])
        client_a.__aenter__ = AsyncMock(return_value=client_a)
        client_a.__aexit__ = AsyncMock(return_value=False)

        # server-b client
        client_b = AsyncMock()
        client_b.discover_tools = AsyncMock(return_value=[tool_b])
        client_b.__aenter__ = AsyncMock(return_value=client_b)
        client_b.__aexit__ = AsyncMock(return_value=False)

        call_count = [0]

        def _client_factory(uri, **_kwargs):
            call_count[0] += 1
            return client_a if "server-a" in uri else client_b

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=_client_factory,
        ):
            with patch(
                "services.realtime_mcp_bridge._get_filter_tools_for_bundle",
                return_value=lambda tools, **_: tools,
            ):
                result = await bridge.list_realtime_tools()

        names = {t.name for t in result}
        assert len(result) == 2
        assert all("__search" in n for n in names)

    @pytest.mark.asyncio
    async def test_unique_tool_not_prefixed_when_collision_elsewhere(self):
        """Unique tool on one server is not prefixed even if another tool has a collision."""
        tool_shared_a = _make_tool("shared")
        tool_shared_b = _make_tool("shared")
        tool_unique = _make_tool("unique_only_on_a")

        uris = ["http://server-a:8200", "http://server-b:8200"]
        bridge = _make_bridge(server_uris=uris)

        client_a = AsyncMock()
        client_a.discover_tools = AsyncMock(return_value=[tool_shared_a, tool_unique])
        client_a.__aenter__ = AsyncMock(return_value=client_a)
        client_a.__aexit__ = AsyncMock(return_value=False)

        client_b = AsyncMock()
        client_b.discover_tools = AsyncMock(return_value=[tool_shared_b])
        client_b.__aenter__ = AsyncMock(return_value=client_b)
        client_b.__aexit__ = AsyncMock(return_value=False)

        def _client_factory(uri, **_kwargs):
            return client_a if "server-a" in uri else client_b

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=_client_factory,
        ):
            with patch(
                "services.realtime_mcp_bridge._get_filter_tools_for_bundle",
                return_value=lambda tools, **_: tools,
            ):
                result = await bridge.list_realtime_tools()

        names = {t.name for t in result}
        assert "unique_only_on_a" in names
        assert any("shared" in n and "__" in n for n in names)


# ---------------------------------------------------------------------------
# 4. Successful tool call
# ---------------------------------------------------------------------------


class TestCallToolSuccess:
    @pytest.mark.asyncio
    async def test_call_external_server_success(self):
        """call_tool routes through MCPClient and returns content."""
        bridge = _make_bridge(server_uris=["http://srv:8200"])

        # Pre-populate registry
        from services.realtime_mcp_bridge import _ToolEntry

        bridge._registry = {
            "search": _ToolEntry(
                server_id="srv_8200",
                server_uri="http://srv:8200",
                original_name="search",
            )
        }

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={"content": [{"text": "hello result"}]})
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=lambda uri: mock_client,
        ):
            with patch("services.realtime_mcp_bridge._audit_log", new_callable=AsyncMock):
                result = await bridge.call_tool("search", {"q": "test"})

        assert result.is_error is False
        assert "hello result" in result.content

    @pytest.mark.asyncio
    async def test_call_inprocess_fallback(self):
        """call_tool with server_uri=None routes in-process."""
        bridge = _make_bridge()

        from services.realtime_mcp_bridge import _ToolEntry

        bridge._registry = {"kb.search": _ToolEntry(server_id="autobot", server_uri=None, original_name="kb.search")}

        with patch(
            "services.realtime_mcp_bridge.RealtimeMCPBridge._call_inprocess",
            new=AsyncMock(return_value="inprocess result"),
        ):
            with patch("services.realtime_mcp_bridge._audit_log", new_callable=AsyncMock):
                result = await bridge.call_tool("kb.search", {"query": "test"})

        assert result.is_error is False
        assert "inprocess result" in result.content


# ---------------------------------------------------------------------------
# 5. Tool call error
# ---------------------------------------------------------------------------


class TestCallToolError:
    @pytest.mark.asyncio
    async def test_mcp_error_surfaces_as_is_error(self):
        """MCPError from the server returns is_error=True with the message."""
        bridge = _make_bridge(server_uris=["http://srv:8200"])

        from services.realtime_mcp_bridge import _ToolEntry

        bridge._registry = {
            "broken": _ToolEntry(
                server_id="srv_8200",
                server_uri="http://srv:8200",
                original_name="broken",
            )
        }

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=MCPError(code=-32000, message="backend exploded"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=lambda uri: mock_client,
        ):
            with patch("services.realtime_mcp_bridge._audit_log", new_callable=AsyncMock):
                result = await bridge.call_tool("broken", {})

        assert result.is_error is True
        assert "backend exploded" in result.content

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_is_error(self):
        """Calling a tool not in the registry returns is_error=True."""
        bridge = _make_bridge()

        with patch("services.realtime_mcp_bridge._audit_log", new_callable=AsyncMock):
            result = await bridge.call_tool("nonexistent", {})

        assert result.is_error is True
        assert "nonexistent" in result.content


# ---------------------------------------------------------------------------
# 6. Transport down
# ---------------------------------------------------------------------------


class TestTransportDown:
    @pytest.mark.asyncio
    async def test_unreachable_server_skipped_gracefully(self):
        """If a server is down, its tools are omitted and other servers proceed."""
        tool_b = _make_tool("tool_on_b")

        uris = ["http://dead:9999", "http://alive:8200"]
        bridge = _make_bridge(server_uris=uris)

        dead_client = AsyncMock()
        dead_client.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("no connection"))
        dead_client.__aexit__ = AsyncMock(return_value=False)

        alive_client = AsyncMock()
        alive_client.discover_tools = AsyncMock(return_value=[tool_b])
        alive_client.__aenter__ = AsyncMock(return_value=alive_client)
        alive_client.__aexit__ = AsyncMock(return_value=False)

        def _client_factory(uri, **_kwargs):
            return dead_client if "dead" in uri else alive_client

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=_client_factory,
        ):
            with patch(
                "services.realtime_mcp_bridge._get_filter_tools_for_bundle",
                return_value=lambda tools, **_: tools,
            ):
                result = await bridge.list_realtime_tools()

        names = [t.name for t in result]
        assert "tool_on_b" in names

    @pytest.mark.asyncio
    async def test_all_servers_down_returns_empty(self):
        """If all servers are unreachable, list_realtime_tools returns empty list."""
        uris = ["http://dead-a:9999", "http://dead-b:9999"]
        bridge = _make_bridge(server_uris=uris)

        dead_client = AsyncMock()
        dead_client.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("no connection"))
        dead_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=lambda uri: dead_client,
        ):
            with patch(
                "services.realtime_mcp_bridge._get_filter_tools_for_bundle",
                return_value=lambda tools, **_: tools,
            ):
                result = await bridge.list_realtime_tools()

        assert result == []

    @pytest.mark.asyncio
    async def test_transport_exception_on_call_returns_is_error(self):
        """If MCPClient.call_tool raises a generic exception, is_error=True is returned."""
        bridge = _make_bridge(server_uris=["http://srv:8200"])

        from services.realtime_mcp_bridge import _ToolEntry

        bridge._registry = {
            "flaky": _ToolEntry(
                server_id="srv_8200",
                server_uri="http://srv:8200",
                original_name="flaky",
            )
        }

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=OSError("socket closed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "services.realtime_mcp_bridge._get_mcp_client_class",
            return_value=lambda uri: mock_client,
        ):
            with patch("services.realtime_mcp_bridge._audit_log", new_callable=AsyncMock):
                result = await bridge.call_tool("flaky", {})

        assert result.is_error is True
        assert "socket closed" in result.content
