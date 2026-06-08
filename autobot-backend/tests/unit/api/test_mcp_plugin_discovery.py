# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for MCP bridge plugin discovery and toggle logic (Issue #4462)."""

from dataclasses import fields
from unittest.mock import AsyncMock, patch

import pytest

from services.mcp_bridge_manifest import MCPBridgeManifest

# ---------------------------------------------------------------------------
# MCPBridgeManifest dataclass tests
# ---------------------------------------------------------------------------


def test_manifest_required_fields():
    m = MCPBridgeManifest(name="test_mcp", version="1.2.3", description="A test bridge")
    assert m.name == "test_mcp"
    assert m.version == "1.2.3"
    assert m.description == "A test bridge"
    assert m.features == []
    assert m.endpoint is None
    assert m.resource_limits is None


def test_manifest_optional_fields():
    m = MCPBridgeManifest(
        name="test_mcp",
        version="1.0.0",
        description="desc",
        features=["feat_a", "feat_b"],
        endpoint="/api/test/mcp/tools",
        resource_limits={"max_connections": 10},
    )
    assert m.features == ["feat_a", "feat_b"]
    assert m.endpoint == "/api/test/mcp/tools"
    assert m.resource_limits == {"max_connections": 10}


def test_manifest_field_names():
    field_names = {f.name for f in fields(MCPBridgeManifest)}
    assert field_names == {"name", "version", "description", "features", "endpoint", "resource_limits"}


# ---------------------------------------------------------------------------
# discover_bridges tests
# ---------------------------------------------------------------------------


def test_discover_bridges_returns_all():
    from api.mcp_registry import _BRIDGE_MODULE_REGISTRY, discover_bridges

    result = discover_bridges()
    assert len(result) == len(_BRIDGE_MODULE_REGISTRY)


def test_discover_bridges_structure():
    from api.mcp_registry import discover_bridges

    result = discover_bridges()
    for entry in result:
        name, desc, endpoint, features = entry
        assert isinstance(name, str) and name
        assert isinstance(desc, str)
        assert isinstance(endpoint, str)
        assert isinstance(features, list)


def test_discover_bridges_known_names():
    from api.mcp_registry import discover_bridges

    result = discover_bridges()
    names = {entry[0] for entry in result}
    expected = {
        "knowledge_mcp",
        "vnc_mcp",
        "sequential_thinking_mcp",
        "structured_thinking_mcp",
        "filesystem_mcp",
        "browser_mcp",
        "http_client_mcp",
        "database_mcp",
        "git_mcp",
        "prometheus_mcp",
        "redis_mcp",
    }
    assert names == expected


def test_discover_bridges_manifest_registry_populated():
    from api.mcp_registry import _MANIFEST_REGISTRY, discover_bridges

    discover_bridges()
    assert len(_MANIFEST_REGISTRY) >= 11
    for name, (manifest, module_path) in _MANIFEST_REGISTRY.items():
        assert isinstance(manifest, MCPBridgeManifest)
        assert manifest.name == name


# ---------------------------------------------------------------------------
# MCPBridgeToggleService tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_bridge_enabled_default_true():
    """Bridge is enabled by default when key absent in Redis."""
    from api.mcp_registry import MCPBridgeToggleService

    svc = MCPBridgeToggleService()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with patch.object(svc, "_get_redis", return_value=mock_redis):
        result = await svc.is_bridge_enabled("knowledge_mcp")

    assert result is True


@pytest.mark.asyncio
async def test_is_bridge_enabled_false_when_set():
    """Bridge returns False after being explicitly disabled."""
    from api.mcp_registry import MCPBridgeToggleService

    svc = MCPBridgeToggleService()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"false")

    with patch.object(svc, "_get_redis", return_value=mock_redis):
        result = await svc.is_bridge_enabled("knowledge_mcp")

    assert result is False


@pytest.mark.asyncio
async def test_is_bridge_enabled_true_when_set():
    """Bridge returns True when explicitly enabled."""
    from api.mcp_registry import MCPBridgeToggleService

    svc = MCPBridgeToggleService()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=b"true")

    with patch.object(svc, "_get_redis", return_value=mock_redis):
        result = await svc.is_bridge_enabled("knowledge_mcp")

    assert result is True


@pytest.mark.asyncio
async def test_set_bridge_enabled_calls_redis_set():
    from api.mcp_registry import MCPBridgeToggleService

    svc = MCPBridgeToggleService()
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock()

    with patch.object(svc, "_get_redis", return_value=mock_redis):
        await svc.set_bridge_enabled("browser_mcp", False)

    mock_redis.set.assert_awaited_once_with("mcp_bridge:enabled:browser_mcp", "false")


@pytest.mark.asyncio
async def test_is_bridge_enabled_returns_true_on_redis_error():
    """Fail-safe: enabled=True when Redis is unavailable."""
    from api.mcp_registry import MCPBridgeToggleService

    svc = MCPBridgeToggleService()

    with patch.object(svc, "_get_redis", side_effect=Exception("Redis down")):
        result = await svc.is_bridge_enabled("git_mcp")

    assert result is True


# ---------------------------------------------------------------------------
# MCP_BRIDGES content tests
# ---------------------------------------------------------------------------


def test_mcp_bridges_populated():
    from api.mcp_registry import _BRIDGE_MODULE_REGISTRY, MCP_BRIDGES

    assert len(MCP_BRIDGES) == len(_BRIDGE_MODULE_REGISTRY)


def test_mcp_bridges_backward_compat_tuple_format():
    from api.mcp_registry import MCP_BRIDGES

    for entry in MCP_BRIDGES:
        assert len(entry) == 4
        name, desc, endpoint, features = entry
        assert isinstance(name, str)
        assert isinstance(desc, str)
        assert isinstance(endpoint, str)
        assert isinstance(features, list)
