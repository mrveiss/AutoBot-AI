# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for tool SDK base classes — issue #3009.

Verifies BaseTool contract, ToolPermission levels, and ToolResult structure
using the canonical API (ToolMetadata + JSON Schema input_schema).
"""

import pytest

from tool_sdk.base import BaseTool, ToolMetadata, ToolPermission, ToolResult


class _EchoTool(BaseTool):
    metadata = ToolMetadata(
        name="echo",
        description="Echoes input back",
        permission=ToolPermission.PUBLIC,
        tags=["test"],
    )
    input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    }

    async def execute(self, validated_input: dict) -> ToolResult:
        return ToolResult(success=True, data=validated_input["message"])


class TestToolPermission:
    def test_permission_values(self) -> None:
        assert ToolPermission.PUBLIC == "public"
        assert ToolPermission.AUTHENTICATED == "authenticated"
        assert ToolPermission.ADMIN == "admin"

    def test_permission_ordering(self) -> None:
        assert ToolPermission.PUBLIC.allows(ToolPermission.PUBLIC)
        assert ToolPermission.AUTHENTICATED.allows(ToolPermission.PUBLIC)
        assert not ToolPermission.PUBLIC.allows(ToolPermission.AUTHENTICATED)
        assert ToolPermission.ADMIN.allows(ToolPermission.AUTHENTICATED)


class TestToolResult:
    def test_success_result(self) -> None:
        result = ToolResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self) -> None:
        result = ToolResult(success=False, error="Something failed")
        assert result.success is False
        assert result.error == "Something failed"
        assert result.data is None

    def test_duration_ms_default(self) -> None:
        result = ToolResult(success=True)
        assert result.duration_ms == 0.0


class TestBaseTool:
    @pytest.mark.asyncio
    async def test_echo_tool_execute(self) -> None:
        tool = _EchoTool()
        result = await tool.execute({"message": "hello"})
        assert result.success is True
        assert result.data == "hello"

    def test_tool_attributes(self) -> None:
        tool = _EchoTool()
        assert tool.metadata.name == "echo"
        assert tool.metadata.description == "Echoes input back"
        assert tool.metadata.permission == ToolPermission.PUBLIC
        assert tool.input_schema["properties"]["message"]["type"] == "string"

    def test_input_validation_rejects_missing_field(self) -> None:
        from tool_sdk.base import ToolInputError

        tool = _EchoTool()
        with pytest.raises(ToolInputError):
            tool.validate_input({})
