# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for MCPDispatcher — dynamic MCP tool discovery and dispatch (#2513).

Coverage:
- Tool cache lookup (empty and populated)
- Dispatch of unknown tool returns error dict
- Dispatch of known tool with successful bridge response
- Dispatch of known tool with failing bridge response
- get_tool_definitions() formats correctly
- refresh_tool_cache() handles registry HTTP errors gracefully
- Cache TTL triggers refresh after expiry (#2598)
- RBAC filtering hides admin-only tools from non-admin callers (#2598)
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.mcp_dispatch import MCPDispatcher, get_mcp_dispatcher
from tests.test_helpers import get_test_backend_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_TOOL = {
    "name": "search_knowledge_base",
    "description": "Search the knowledge base",
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
    "bridge": "knowledge_mcp",
    "endpoint": get_test_backend_url() + "/api/knowledge/mcp/search_knowledge_base",
    "features": ["search"],
}


def _make_dispatcher_with_cache(*tools) -> MCPDispatcher:
    """Return a dispatcher pre-loaded with the given tool dicts."""
    d = MCPDispatcher()
    d._tool_cache = {t["name"]: t for t in tools}
    d._cache_loaded = True
    return d


# ---------------------------------------------------------------------------
# Cache lookup
# ---------------------------------------------------------------------------


def test_find_tool_returns_none_when_empty() -> None:
    """Empty cache should return None for any name."""
    d = MCPDispatcher()
    assert d.find_tool("search_knowledge_base") is None


def test_find_tool_returns_cached_tool() -> None:
    """After populating the cache manually, find_tool should return the entry."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL)
    result = d.find_tool("search_knowledge_base")
    assert result is not None
    assert result["bridge"] == "knowledge_mcp"


# ---------------------------------------------------------------------------
# Dispatch — unknown tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_returns_error() -> None:
    """Dispatching a tool not in cache should return success=False."""
    d = _make_dispatcher_with_cache()  # empty cache
    result = await d.dispatch("nonexistent_tool", {})
    assert result["success"] is False
    assert "nonexistent_tool" in result["result"]
    assert result["bridge"] is None


# ---------------------------------------------------------------------------
# Dispatch — successful bridge call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_calls_bridge_endpoint() -> None:
    """A known tool should call the bridge endpoint and return success=True."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL)

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"results": ["doc1"]})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = AsyncMock(return_value=mock_response)

    with patch("services.mcp_dispatch.get_http_client", return_value=mock_session):
        result = await d.dispatch("search_knowledge_base", {"query": "test"})

    assert result["success"] is True
    assert result["bridge"] == "knowledge_mcp"
    assert result["result"] == {"results": ["doc1"]}


# ---------------------------------------------------------------------------
# Dispatch — bridge error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_handles_bridge_error() -> None:
    """When the bridge returns a non-200 status, success should be False."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL)

    mock_response = AsyncMock()
    mock_response.status = 503
    mock_response.text = AsyncMock(return_value="Service Unavailable")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = AsyncMock(return_value=mock_response)

    with patch("services.mcp_dispatch.get_http_client", return_value=mock_session):
        result = await d.dispatch("search_knowledge_base", {})

    assert result["success"] is False
    assert "503" in result["result"]
    assert result["bridge"] == "knowledge_mcp"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def test_get_tool_definitions_formats_correctly() -> None:
    """Tool definitions should include bridge prefix in description."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL)
    defs = d.get_tool_definitions()
    assert len(defs) == 1
    defn = defs[0]
    assert defn["name"] == "search_knowledge_base"
    assert defn["description"].startswith("[knowledge_mcp]")
    assert "Search the knowledge base" in defn["description"]
    assert defn["parameters"] == _SAMPLE_TOOL["input_schema"]


# ---------------------------------------------------------------------------
# refresh_tool_cache — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_cache_handles_registry_unavailable() -> None:
    """refresh_tool_cache() should return 0 and not crash when registry is down."""
    d = MCPDispatcher()

    import aiohttp

    with patch(
        "services.mcp_dispatch.get_http_client",
        side_effect=aiohttp.ClientConnectionError("refused"),
    ):
        count = await d.refresh_tool_cache()

    assert count == 0
    assert d._cache_loaded is False


@pytest.mark.asyncio
async def test_refresh_cache_handles_non_200_response() -> None:
    """refresh_tool_cache() should return 0 when registry returns non-200."""
    d = MCPDispatcher()

    mock_response = AsyncMock()
    mock_response.status = 503
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_response)

    with patch("services.mcp_dispatch.get_http_client", return_value=mock_session):
        count = await d.refresh_tool_cache()

    assert count == 0
    assert not d._cache_loaded


@pytest.mark.asyncio
async def test_refresh_cache_populates_tool_dict() -> None:
    """refresh_tool_cache() should populate _tool_cache from registry response."""
    d = MCPDispatcher()

    registry_response = {
        "tools": [_SAMPLE_TOOL],
        "total_tools": 1,
    }
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=registry_response)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get = AsyncMock(return_value=mock_response)

    with patch("services.mcp_dispatch.get_http_client", return_value=mock_session):
        count = await d.refresh_tool_cache()

    assert count == 1
    assert d._cache_loaded is True
    assert "search_knowledge_base" in d._tool_cache


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


def test_get_mcp_dispatcher_returns_singleton() -> None:
    """get_mcp_dispatcher() should always return the same instance."""
    a = get_mcp_dispatcher()
    b = get_mcp_dispatcher()
    assert a is b


# ---------------------------------------------------------------------------
# Cache TTL (#2598)
# ---------------------------------------------------------------------------

_ADMIN_TOOL = {
    "name": "redis_client_list",
    "description": "List all Redis clients",
    "input_schema": {},
    "bridge": "redis_mcp",
    "endpoint": get_test_backend_url() + "/api/redis/mcp/client_list",
    "features": [],
}


@pytest.mark.asyncio
async def test_cache_ttl_triggers_refresh():
    """dispatch() should call refresh_tool_cache when cache is older than TTL (#2598)."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL)
    # Wind back timestamp so TTL appears expired
    d._cache_timestamp = time.monotonic() - (d.CACHE_TTL_SECONDS + 1)

    refresh_called = []

    async def fake_refresh():
        refresh_called.append(True)
        d._cache_loaded = True
        d._cache_timestamp = time.monotonic()
        return 1

    d.refresh_tool_cache = fake_refresh  # type: ignore[method-assign]

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"results": []})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.post = AsyncMock(return_value=mock_response)

    with patch("services.mcp_dispatch.get_http_client", return_value=mock_session):
        await d.dispatch("search_knowledge_base", {})

    assert refresh_called, "Expected refresh_tool_cache to be called after TTL expiry"


@pytest.mark.asyncio
async def test_cache_ttl_does_not_refresh_when_fresh():
    """dispatch() should NOT call refresh_tool_cache when cache is still within TTL (#2598)."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL)
    d._cache_timestamp = time.monotonic()  # just refreshed

    refresh_called = []

    async def fake_refresh():
        refresh_called.append(True)
        return 1

    d.refresh_tool_cache = fake_refresh  # type: ignore[method-assign]

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"results": []})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.post = AsyncMock(return_value=mock_response)

    with patch("services.mcp_dispatch.get_http_client", return_value=mock_session):
        await d.dispatch("search_knowledge_base", {})

    assert not refresh_called, "Expected no refresh when cache is fresh"


# ---------------------------------------------------------------------------
# RBAC filtering (#2598)
# ---------------------------------------------------------------------------


def test_get_tool_definitions_filters_admin_tools_for_user() -> None:
    """Admin-only tools should be hidden from role='user' (#2598)."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL, _ADMIN_TOOL)
    defs = d.get_tool_definitions(role="user")
    names = [t["name"] for t in defs]
    assert "search_knowledge_base" in names
    assert "redis_client_list" not in names


def test_get_tool_definitions_shows_all_for_admin() -> None:
    """All tools including admin-only should be visible for role='admin' (#2598)."""
    d = _make_dispatcher_with_cache(_SAMPLE_TOOL, _ADMIN_TOOL)
    defs = d.get_tool_definitions(role="admin")
    names = [t["name"] for t in defs]
    assert "search_knowledge_base" in names
    assert "redis_client_list" in names


@pytest.mark.asyncio
async def test_dispatch_rejects_admin_tool_for_user() -> None:
    """dispatch() should return success=False for admin-only tool when role='user' (#2598)."""
    d = _make_dispatcher_with_cache(_ADMIN_TOOL)
    d._cache_timestamp = time.monotonic()  # keep cache fresh to avoid network call

    result = await d.dispatch("redis_client_list", {}, role="user")

    assert result["success"] is False
    assert "admin" in result["result"].lower()
    assert result["bridge"] is None
