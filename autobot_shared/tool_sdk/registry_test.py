# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for ToolSDKRegistry — issue #3009.

Verifies register(), get(), list_tools(), execute(), to_openapi_spec(),
singleton behaviour, and the get_tool_sdk_registry alias.
"""

import pytest

from tool_sdk import get_tool_sdk_registry
from tool_sdk.base import BaseTool, ToolMetadata, ToolPermission, ToolResult
from tool_sdk.registry import (
    PermissionDeniedError,
    ToolNotFoundError,
    ToolSDKRegistry,
    get_tool_registry,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _PingTool(BaseTool):
    """Returns pong — minimal public tool for registry tests."""

    metadata = ToolMetadata(
        name="ping",
        description="Returns pong",
        permission=ToolPermission.PUBLIC,
        tags=["system"],
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, validated_input: dict) -> ToolResult:
        return ToolResult(success=True, data="pong")


class _AdminResetTool(BaseTool):
    """Admin-only reset tool for permission tests."""

    metadata = ToolMetadata(
        name="admin_reset",
        description="Admin-only reset",
        permission=ToolPermission.ADMIN,
        tags=["admin"],
    )
    input_schema = {
        "type": "object",
        "properties": {
            "target": {"type": "string"},
        },
        "required": ["target"],
    }

    async def execute(self, validated_input: dict) -> ToolResult:
        return ToolResult(success=True, data=f"reset {validated_input['target']}")


def _fresh_registry() -> ToolSDKRegistry:
    """Return a brand-new (non-singleton) registry for test isolation."""
    return ToolSDKRegistry()


# ---------------------------------------------------------------------------
# TestToolSDKRegistry — register / get
# ---------------------------------------------------------------------------


class TestRegisterAndGet:
    def test_register_and_get_returns_instance(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        tool = reg.get("ping")
        assert isinstance(tool, _PingTool)

    def test_get_returns_fresh_instance_each_call(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        assert reg.get("ping") is not reg.get("ping")

    def test_get_nonexistent_raises(self) -> None:
        reg = _fresh_registry()
        with pytest.raises(ToolNotFoundError):
            reg.get("nonexistent")

    def test_duplicate_registration_raises(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_PingTool)

    def test_non_basetool_raises(self) -> None:
        reg = _fresh_registry()
        with pytest.raises(TypeError):
            reg.register(object)  # type: ignore[arg-type]

    def test_unregister_removes_tool(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        reg.unregister("ping")
        with pytest.raises(ToolNotFoundError):
            reg.get("ping")


# ---------------------------------------------------------------------------
# TestListTools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_list_tools_returns_metadata(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        reg.register(_AdminResetTool)
        metas = reg.list_tools()
        names = [m.name for m in metas]
        assert "ping" in names
        assert "admin_reset" in names

    def test_list_tools_sorted_by_name(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminResetTool)
        reg.register(_PingTool)
        names = [m.name for m in reg.list_tools()]
        assert names == sorted(names)

    def test_permission_filter_excludes_higher_permission(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        reg.register(_AdminResetTool)
        visible = [m.name for m in reg.list_tools(ToolPermission.AUTHENTICATED)]
        assert "ping" in visible
        assert "admin_reset" not in visible

    def test_admin_filter_includes_admin_tools(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        reg.register(_AdminResetTool)
        visible = [m.name for m in reg.list_tools(ToolPermission.ADMIN)]
        assert "ping" in visible
        assert "admin_reset" in visible


# ---------------------------------------------------------------------------
# TestExecute
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        result = await reg.execute("ping", {}, ToolPermission.PUBLIC)
        assert result.success is True
        assert result.data == "pong"

    @pytest.mark.asyncio
    async def test_permission_denied_raises(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminResetTool)
        with pytest.raises(PermissionDeniedError):
            await reg.execute("admin_reset", {"target": "x"}, ToolPermission.PUBLIC)

    @pytest.mark.asyncio
    async def test_admin_caller_can_execute_admin_tool(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminResetTool)
        result = await reg.execute("admin_reset", {"target": "db"}, ToolPermission.ADMIN)
        assert result.success is True
        assert "db" in result.data

    @pytest.mark.asyncio
    async def test_invalid_input_returns_failure_result(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminResetTool)
        # Missing required "target" field
        result = await reg.execute("admin_reset", {}, ToolPermission.ADMIN)
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self) -> None:
        reg = _fresh_registry()
        with pytest.raises(ToolNotFoundError):
            await reg.execute("ghost", {}, ToolPermission.PUBLIC)

    @pytest.mark.asyncio
    async def test_duration_ms_populated(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        result = await reg.execute("ping", {}, ToolPermission.PUBLIC)
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# TestOpenAPISpec
# ---------------------------------------------------------------------------


class TestOpenAPISpec:
    def test_spec_contains_tools_key(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        spec = reg.to_openapi_spec()
        assert "tools" in spec
        assert len(spec["tools"]) == 1

    def test_spec_tool_fields(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        tool_def = reg.to_openapi_spec()["tools"][0]
        assert tool_def["name"] == "ping"
        assert tool_def["description"] == "Returns pong"
        assert tool_def["permission"] == "public"
        assert tool_def["tags"] == ["system"]
        assert "parameters" in tool_def

    def test_spec_respects_permission_filter(self) -> None:
        reg = _fresh_registry()
        reg.register(_PingTool)
        reg.register(_AdminResetTool)
        spec = reg.to_openapi_spec(permission_filter=ToolPermission.AUTHENTICATED)
        names = [t["name"] for t in spec["tools"]]
        assert "ping" in names
        assert "admin_reset" not in names

    def test_spec_sorted_by_name(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminResetTool)
        reg.register(_PingTool)
        names = [t["name"] for t in reg.to_openapi_spec()["tools"]]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_tool_registry_returns_same_instance(self) -> None:
        a = get_tool_registry()
        b = get_tool_registry()
        assert a is b

    def test_get_tool_sdk_registry_alias_same_instance(self) -> None:
        a = get_tool_sdk_registry()
        b = get_tool_registry()
        assert a is b
