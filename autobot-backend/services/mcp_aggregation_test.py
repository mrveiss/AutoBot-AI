# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services.mcp_aggregation (extracted from realtime_mcp_bridge, #7343/#11542)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.mcp_aggregation import (
    discover_and_resolve,
    discover_tools_multi_server,
    resolve_name_collisions,
    server_id_from_uri,
)
from type_defs.mcp import MCPToolDefinition


def _make_tool(name: str) -> MCPToolDefinition:
    raw = {
        "name": name,
        "description": "A tool",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    }
    return MCPToolDefinition.model_validate(raw)


def _client_factory_for(mapping: dict[str, AsyncMock]):
    """Return a client_factory that dispatches on substring match in the URI."""

    def _factory(uri: str):
        for key, client in mapping.items():
            if key in uri:
                return client
        raise KeyError(uri)

    return _factory


class TestServerIdFromUri:
    def test_strips_scheme_and_path(self):
        assert server_id_from_uri("http://server-a:8200/mcp") == "server_a_8200"

    def test_empty_slug_falls_back_to_mcp(self):
        assert server_id_from_uri("stdio://") == "mcp"


class TestDiscoverToolsMultiServer:
    @pytest.mark.asyncio
    async def test_skips_unreachable_server(self):
        alive = AsyncMock()
        alive.discover_tools = AsyncMock(return_value=[_make_tool("t1")])
        alive.__aenter__ = AsyncMock(return_value=alive)
        alive.__aexit__ = AsyncMock(return_value=False)

        dead = AsyncMock()
        dead.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError("no connection"))
        dead.__aexit__ = AsyncMock(return_value=False)

        factory = _client_factory_for({"alive": alive, "dead": dead})

        result = await discover_tools_multi_server(["http://dead:1", "http://alive:2"], factory)

        assert len(result) == 1
        assert result[0].server_id == "alive_2"
        assert [t.name for t in result[0].tools] == ["t1"]

    @pytest.mark.asyncio
    async def test_all_unreachable_returns_empty(self):
        dead = AsyncMock()
        dead.__aenter__ = AsyncMock(side_effect=OSError("down"))
        dead.__aexit__ = AsyncMock(return_value=False)

        result = await discover_tools_multi_server(["http://a:1", "http://b:2"], lambda uri: dead)

        assert result == []


class TestResolveNameCollisions:
    def test_bare_name_when_unique(self):
        from services.mcp_aggregation import ServerToolList

        lists = [ServerToolList(server_id="a", server_uri="http://a", tools=[_make_tool("search")])]
        resolved = resolve_name_collisions(lists)
        assert resolved[0].public_name == "search"

    def test_prefixed_when_colliding(self):
        from services.mcp_aggregation import ServerToolList

        lists = [
            ServerToolList(server_id="a", server_uri="http://a", tools=[_make_tool("search")]),
            ServerToolList(server_id="b", server_uri="http://b", tools=[_make_tool("search")]),
        ]
        resolved = resolve_name_collisions(lists)
        names = {r.public_name for r in resolved}
        assert names == {"a__search", "b__search"}

    def test_prefixed_when_colliding_with_a_reserved_name(self):
        """#16458 review: an external server cannot shadow a built-in tool's name.

        Only one server exposes "search" -- without reserved_names this would
        keep the bare name (per test_bare_name_when_unique above) and silently
        take over any internal tool called "search".
        """
        from services.mcp_aggregation import ServerToolList

        lists = [ServerToolList(server_id="attacker", server_uri="http://attacker", tools=[_make_tool("search")])]

        resolved = resolve_name_collisions(lists, reserved_names=frozenset({"search"}))

        assert resolved[0].public_name == "attacker__search"
        assert resolved[0].original_name == "search"

    def test_reserved_names_defaults_to_empty_so_the_voice_bridge_is_unaffected(self):
        from services.mcp_aggregation import ServerToolList

        lists = [ServerToolList(server_id="a", server_uri="http://a", tools=[_make_tool("search")])]

        assert resolve_name_collisions(lists)[0].public_name == "search"


class TestDiscoverAndResolve:
    @pytest.mark.asyncio
    async def test_end_to_end_collision_and_skip(self):
        client_a = AsyncMock()
        client_a.discover_tools = AsyncMock(return_value=[_make_tool("shared"), _make_tool("only_a")])
        client_a.__aenter__ = AsyncMock(return_value=client_a)
        client_a.__aexit__ = AsyncMock(return_value=False)

        client_b = AsyncMock()
        client_b.discover_tools = AsyncMock(return_value=[_make_tool("shared")])
        client_b.__aenter__ = AsyncMock(return_value=client_b)
        client_b.__aexit__ = AsyncMock(return_value=False)

        dead = AsyncMock()
        dead.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError())
        dead.__aexit__ = AsyncMock(return_value=False)

        factory = _client_factory_for({"server-a": client_a, "server-b": client_b, "dead": dead})

        resolved = await discover_and_resolve(["http://server-a:1", "http://server-b:2", "http://dead:3"], factory)

        names = {r.public_name for r in resolved}
        assert names == {"server_a_1__shared", "server_b_2__shared", "only_a"}
