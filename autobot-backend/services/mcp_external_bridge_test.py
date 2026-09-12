# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services.mcp_external_bridge (#11542).

Mirrors services/realtime_mcp_bridge_test.py's coverage shape: collision
resolution, skip-unreachable-server, and call-routing — for the chat-tool
bridge instead of the voice bridge.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services.mcp_external_bridge import MCPExternalBridge
from services.mcp_external_servers import MCPServerConfig
from type_defs.mcp import MCPToolDefinition


def _make_tool(name: str) -> MCPToolDefinition:
    raw = {"name": name, "description": "A tool", "inputSchema": {"type": "object", "properties": {}, "required": []}}
    return MCPToolDefinition.model_validate(raw)


def _stdio_server(server_id="s1", enabled=True) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id, name="fs", transport="stdio", owner_id="admin-1", command="npx -y pkg", enabled=enabled
    )


def _remote_server(server_id="s2", url="https://mcp-a.example.com/mcp", enabled=True) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id, name="remote", transport="streamable_http", owner_id="admin-1", url=url, enabled=enabled
    )


@pytest.fixture(autouse=True)
def _stub_audit():
    with patch("services.mcp_external_bridge._audit_log", new_callable=AsyncMock):
        yield


class TestListTools:
    @pytest.mark.asyncio
    async def test_no_servers_returns_empty(self):
        bridge = MCPExternalBridge()
        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(return_value=[])
            tools = await bridge.list_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_disabled_servers_excluded(self):
        bridge = MCPExternalBridge()
        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(return_value=[_stdio_server(enabled=False)])
            tools = await bridge.list_tools()
        assert tools == []

    @pytest.mark.asyncio
    async def test_single_server_tool_keeps_bare_name(self):
        bridge = MCPExternalBridge()
        mock_client = AsyncMock()
        mock_client.discover_tools = AsyncMock(return_value=[_make_tool("search")])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(return_value=[_stdio_server()])
            with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=lambda uri, **_: mock_client):
                tools = await bridge.list_tools()

        assert [t.name for t in tools] == ["search"]

    @pytest.mark.asyncio
    async def test_collision_across_two_servers_prefixes_both(self):
        bridge = MCPExternalBridge()
        client_a = AsyncMock()
        client_a.discover_tools = AsyncMock(return_value=[_make_tool("search")])
        client_a.__aenter__ = AsyncMock(return_value=client_a)
        client_a.__aexit__ = AsyncMock(return_value=False)

        client_b = AsyncMock()
        client_b.discover_tools = AsyncMock(return_value=[_make_tool("search")])
        client_b.__aenter__ = AsyncMock(return_value=client_b)
        client_b.__aexit__ = AsyncMock(return_value=False)

        def _factory(uri, **_kwargs):
            return client_a if "mcp-a" in uri else client_b

        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(
                return_value=[
                    _remote_server(server_id="s1", url="https://mcp-a.example.com/mcp"),
                    _remote_server(server_id="s2", url="https://mcp-b.example.com/mcp"),
                ]
            )
            with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=_factory):
                with patch("services.mcp_external_bridge.instance_host_egress", return_value=False):
                    tools = await bridge.list_tools()

        names = {t.name for t in tools}
        assert all("__search" in n for n in names)
        assert len(tools) == 2

    @pytest.mark.asyncio
    async def test_unreachable_server_skipped_gracefully(self):
        bridge = MCPExternalBridge()
        alive_client = AsyncMock()
        alive_client.discover_tools = AsyncMock(return_value=[_make_tool("alive_tool")])
        alive_client.__aenter__ = AsyncMock(return_value=alive_client)
        alive_client.__aexit__ = AsyncMock(return_value=False)

        dead_client = AsyncMock()
        dead_client.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError())
        dead_client.__aexit__ = AsyncMock(return_value=False)

        def _factory(uri, **_kwargs):
            return dead_client if "dead" in uri else alive_client

        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(
                return_value=[
                    _remote_server(server_id="s1", url="https://dead.example.com/mcp"),
                    _remote_server(server_id="s2", url="https://alive.example.com/mcp"),
                ]
            )
            with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=_factory):
                with patch("services.mcp_external_bridge.instance_host_egress", return_value=False):
                    tools = await bridge.list_tools()

        assert [t.name for t in tools] == ["alive_tool"]


class TestCallTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error_without_raising(self):
        bridge = MCPExternalBridge()
        result = await bridge.call_tool("nope", {})
        assert result.success is False
        assert "Unknown external MCP tool" in result.error

    @pytest.mark.asyncio
    async def test_call_routes_to_owning_server(self):
        bridge = MCPExternalBridge()
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={"ok": True})
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        from services.mcp_external_bridge import _ExternalToolEntry

        bridge._registry = {
            "search": _ExternalToolEntry(
                server_uri="https://mcp-a.example.com/mcp",
                original_name="search",
                guard_egress=False,
                extra_headers={},
            )
        }

        with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=lambda uri, **_: mock_client):
            result = await bridge.call_tool("search", {"q": "x"})

        assert result.success is True
        assert result.result == {"ok": True}
        mock_client.call_tool.assert_awaited_once_with("search", {"q": "x"})

    @pytest.mark.asyncio
    async def test_call_transport_error_returns_failure(self):
        bridge = MCPExternalBridge()
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=OSError("socket closed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        from services.mcp_external_bridge import _ExternalToolEntry

        bridge._registry = {
            "flaky": _ExternalToolEntry(
                server_uri="https://mcp-a.example.com/mcp",
                original_name="flaky",
                guard_egress=False,
                extra_headers={},
            )
        }

        with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=lambda uri, **_: mock_client):
            result = await bridge.call_tool("flaky", {})

        assert result.success is False
        assert "socket closed" in result.error


class TestResourcePolicy:
    """cpu/memory/nofile rlimits for stdio servers (#3229)."""

    @pytest.mark.asyncio
    async def test_stdio_server_gets_a_resource_policy(self):
        bridge = MCPExternalBridge()
        mock_client = AsyncMock()
        mock_client.discover_tools = AsyncMock(return_value=[_make_tool("fs_read")])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        captured_kwargs = {}

        def _factory(uri, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_client

        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(return_value=[_stdio_server()])
            with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=_factory):
                await bridge.list_tools()

        assert captured_kwargs["resource_policy"] is not None
        assert bridge._registry["fs_read"].resource_policy is not None

    @pytest.mark.asyncio
    async def test_remote_server_gets_no_resource_policy(self):
        bridge = MCPExternalBridge()
        mock_client = AsyncMock()
        mock_client.discover_tools = AsyncMock(return_value=[_make_tool("remote_search")])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        captured_kwargs = {}

        def _factory(uri, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_client

        with patch("services.mcp_external_bridge.get_mcp_external_server_store") as get_store:
            get_store.return_value.list = AsyncMock(return_value=[_remote_server()])
            with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=_factory):
                with patch("services.mcp_external_bridge.instance_host_egress", return_value=False):
                    await bridge.list_tools()

        assert captured_kwargs["resource_policy"] is None

    @pytest.mark.asyncio
    async def test_call_tool_reuses_the_resource_policy_from_discovery(self):
        bridge = MCPExternalBridge()
        from services.mcp_external_bridge import _ExternalToolEntry
        from services.mcp_isolation_config import policy_for

        policy = policy_for("s1")
        bridge._registry = {
            "fs_read": _ExternalToolEntry(
                server_uri="stdio://npx -y pkg",
                original_name="fs_read",
                guard_egress=None,
                extra_headers={},
                resource_policy=policy,
            )
        }

        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value="ok")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        captured_kwargs = {}

        def _factory(uri, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_client

        with patch("services.mcp_external_bridge._get_mcp_client_class", return_value=_factory):
            await bridge.call_tool("fs_read", {})

        assert captured_kwargs["resource_policy"] is policy
