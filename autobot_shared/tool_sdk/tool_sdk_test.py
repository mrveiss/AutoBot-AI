# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for the Tool SDK — BaseTool, ToolSDKRegistry, and validation (#3018).

Run with:
    pytest autobot_shared/tool_sdk/tool_sdk_test.py -v
"""

import pytest

from tool_sdk.base import (
    BaseTool,
    ToolInputError,
    ToolMetadata,
    ToolPermission,
    ToolResult,
    _validate_against_schema,
)
from tool_sdk.registry import (
    PermissionDeniedError,
    ToolNotFoundError,
    ToolSDKRegistry,
    get_tool_registry,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _EchoTool(BaseTool):
    """Returns the input text unchanged."""

    metadata = ToolMetadata(
        name="echo",
        description="Echo the input text.",
        version="1.0.0",
        permission=ToolPermission.PUBLIC,
        tags=["utility"],
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
        "additionalProperties": False,
    }

    async def execute(self, validated_input: dict) -> ToolResult:
        return ToolResult(success=True, data={"text": validated_input["text"]})


class _AdminTool(BaseTool):
    """A privileged tool that requires admin permission."""

    metadata = ToolMetadata(
        name="admin_op",
        description="An admin-only operation.",
        permission=ToolPermission.ADMIN,
        tags=["admin"],
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, validated_input: dict) -> ToolResult:
        return ToolResult(success=True, data={"done": True})


class _FailingTool(BaseTool):
    """Always raises inside execute() to test error wrapping."""

    metadata = ToolMetadata(
        name="failing_tool",
        description="Always raises.",
        permission=ToolPermission.AUTHENTICATED,
        tags=[],
    )
    input_schema = {"type": "object", "properties": {}, "required": []}

    async def execute(self, validated_input: dict) -> ToolResult:
        raise RuntimeError("deliberate failure")


def _fresh_registry() -> ToolSDKRegistry:
    return ToolSDKRegistry()


# ---------------------------------------------------------------------------
# ToolPermission.allows()
# ---------------------------------------------------------------------------


class TestToolPermissionAllows:
    def test_public_allows_public(self) -> None:
        assert ToolPermission.PUBLIC.allows(ToolPermission.PUBLIC)

    def test_authenticated_allows_public(self) -> None:
        assert ToolPermission.AUTHENTICATED.allows(ToolPermission.PUBLIC)

    def test_authenticated_allows_authenticated(self) -> None:
        assert ToolPermission.AUTHENTICATED.allows(ToolPermission.AUTHENTICATED)

    def test_authenticated_denies_admin(self) -> None:
        assert not ToolPermission.AUTHENTICATED.allows(ToolPermission.ADMIN)

    def test_admin_allows_admin(self) -> None:
        assert ToolPermission.ADMIN.allows(ToolPermission.ADMIN)

    def test_admin_denies_system(self) -> None:
        assert not ToolPermission.ADMIN.allows(ToolPermission.SYSTEM)

    def test_system_allows_all(self) -> None:
        for perm in ToolPermission:
            assert ToolPermission.SYSTEM.allows(perm)

    def test_public_denies_authenticated(self) -> None:
        assert not ToolPermission.PUBLIC.allows(ToolPermission.AUTHENTICATED)


# ---------------------------------------------------------------------------
# BaseTool class contract enforcement
# ---------------------------------------------------------------------------


class TestBaseToolContract:
    def test_missing_metadata_raises(self) -> None:
        with pytest.raises(TypeError, match="metadata"):

            class _Bad(BaseTool):
                input_schema = {"type": "object"}

                async def execute(self, validated_input) -> None:
                    pass

    def test_missing_input_schema_raises(self) -> None:
        with pytest.raises(TypeError, match="input_schema"):

            class _Bad(BaseTool):
                metadata = ToolMetadata(name="bad", description="bad")

                async def execute(self, validated_input) -> None:
                    pass

    def test_valid_subclass_instantiates(self) -> None:
        tool = _EchoTool()
        assert tool.metadata.name == "echo"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidateInput:
    def setup_method(self) -> None:
        self.tool = _EchoTool()

    def test_valid_input_passes(self) -> None:
        result = self.tool.validate_input({"text": "hello"})
        assert result == {"text": "hello"}

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ToolInputError, match="text"):
            self.tool.validate_input({})

    def test_wrong_type_raises(self) -> None:
        with pytest.raises(ToolInputError, match="string"):
            self.tool.validate_input({"text": 123})

    def test_additional_property_raises(self) -> None:
        with pytest.raises(ToolInputError, match="Unexpected field"):
            self.tool.validate_input({"text": "hi", "extra": "val"})


class TestValidateAgainstSchema:
    """Unit tests for the _validate_against_schema helper directly."""

    def test_string_min_length(self) -> None:
        schema = {"type": "string", "minLength": 3}
        with pytest.raises(ToolInputError, match="at least"):
            _validate_against_schema("ab", schema)

    def test_string_max_length(self) -> None:
        schema = {"type": "string", "maxLength": 5}
        with pytest.raises(ToolInputError, match="at most"):
            _validate_against_schema("toolong", schema)

    def test_integer_minimum(self) -> None:
        schema = {"type": "integer", "minimum": 1}
        with pytest.raises(ToolInputError, match=">= 1"):
            _validate_against_schema(0, schema)

    def test_integer_maximum(self) -> None:
        schema = {"type": "integer", "maximum": 10}
        with pytest.raises(ToolInputError, match="<= 10"):
            _validate_against_schema(11, schema)

    def test_enum_valid(self) -> None:
        schema = {"type": "string", "enum": ["a", "b"]}
        assert _validate_against_schema("a", schema) == "a"

    def test_enum_invalid(self) -> None:
        schema = {"type": "string", "enum": ["a", "b"]}
        with pytest.raises(ToolInputError, match="must be one of"):
            _validate_against_schema("c", schema)

    def test_nested_object(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "inner": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                }
            },
            "required": ["inner"],
        }
        with pytest.raises(ToolInputError, match="inner.x"):
            _validate_against_schema({"inner": {}}, schema)

    def test_array_items(self) -> None:
        schema = {"type": "array", "items": {"type": "integer"}}
        with pytest.raises(ToolInputError, match="string"):
            _validate_against_schema([1, "oops"], schema)

    def test_number_accepts_float(self) -> None:
        schema = {"type": "number"}
        assert _validate_against_schema(3.14, schema) == 3.14

    def test_number_accepts_int(self) -> None:
        schema = {"type": "number"}
        assert _validate_against_schema(7, schema) == 7


# ---------------------------------------------------------------------------
# ToolSDKRegistry — registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_get(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        tool = reg.get("echo")
        assert isinstance(tool, _EchoTool)

    def test_duplicate_registration_raises(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_EchoTool)

    def test_non_basetool_raises(self) -> None:
        reg = _fresh_registry()
        with pytest.raises(TypeError):
            reg.register(object)  # type: ignore[arg-type]

    def test_get_unknown_raises(self) -> None:
        reg = _fresh_registry()
        with pytest.raises(ToolNotFoundError):
            reg.get("nonexistent")

    def test_unregister(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        reg.unregister("echo")
        with pytest.raises(ToolNotFoundError):
            reg.get("echo")


# ---------------------------------------------------------------------------
# ToolSDKRegistry — list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_returns_all_without_filter(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        reg.register(_AdminTool)
        names = [m.name for m in reg.list_tools()]
        assert "echo" in names
        assert "admin_op" in names

    def test_filter_excludes_higher_permission(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        reg.register(_AdminTool)
        # AUTHENTICATED caller can see PUBLIC tools but not ADMIN tools
        visible = [m.name for m in reg.list_tools(ToolPermission.AUTHENTICATED)]
        assert "echo" in visible
        assert "admin_op" not in visible

    def test_admin_filter_includes_admin_tools(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        reg.register(_AdminTool)
        visible = [m.name for m in reg.list_tools(ToolPermission.ADMIN)]
        assert "echo" in visible
        assert "admin_op" in visible

    def test_results_sorted_by_name(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminTool)
        reg.register(_EchoTool)
        names = [m.name for m in reg.list_tools()]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# ToolSDKRegistry — execute
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        result = await reg.execute("echo", {"text": "hello"}, ToolPermission.PUBLIC)
        assert result.success is True
        assert result.data == {"text": "hello"}
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_permission_denied_raises(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminTool)
        with pytest.raises(PermissionDeniedError):
            await reg.execute("admin_op", {}, ToolPermission.PUBLIC)

    @pytest.mark.asyncio
    async def test_admin_can_call_admin_tool(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminTool)
        result = await reg.execute("admin_op", {}, ToolPermission.ADMIN)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_invalid_input_returns_failure(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        result = await reg.execute("echo", {}, ToolPermission.PUBLIC)
        assert result.success is False
        assert "text" in (result.error or "")

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self) -> None:
        reg = _fresh_registry()
        with pytest.raises(ToolNotFoundError):
            await reg.execute("ghost", {}, ToolPermission.PUBLIC)

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_failure(self) -> None:
        reg = _fresh_registry()
        reg.register(_FailingTool)
        result = await reg.execute("failing_tool", {}, ToolPermission.AUTHENTICATED)
        assert result.success is False
        assert "deliberate failure" in (result.error or "")

    @pytest.mark.asyncio
    async def test_duration_ms_populated(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        result = await reg.execute("echo", {"text": "t"}, ToolPermission.PUBLIC)
        assert result.duration_ms > 0


# ---------------------------------------------------------------------------
# to_openapi_spec
# ---------------------------------------------------------------------------


class TestOpenAPISpec:
    def test_spec_structure(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        spec = reg.to_openapi_spec()
        assert "tools" in spec
        assert len(spec["tools"]) == 1
        tool_def = spec["tools"][0]
        assert tool_def["name"] == "echo"
        assert tool_def["description"] == "Echo the input text."
        assert tool_def["version"] == "1.0.0"
        assert tool_def["permission"] == "public"
        assert tool_def["tags"] == ["utility"]
        assert "parameters" in tool_def

    def test_spec_respects_permission_filter(self) -> None:
        reg = _fresh_registry()
        reg.register(_EchoTool)
        reg.register(_AdminTool)
        spec = reg.to_openapi_spec(permission_filter=ToolPermission.AUTHENTICATED)
        names = [t["name"] for t in spec["tools"]]
        assert "echo" in names
        assert "admin_op" not in names

    def test_spec_sorted_by_name(self) -> None:
        reg = _fresh_registry()
        reg.register(_AdminTool)
        reg.register(_EchoTool)
        spec = reg.to_openapi_spec()
        names = [t["name"] for t in spec["tools"]]
        assert names == sorted(names)

    def test_to_openapi_schema_on_instance(self) -> None:
        tool = _EchoTool()
        schema = tool.to_openapi_schema()
        assert schema["name"] == "echo"
        assert "parameters" in schema


# ---------------------------------------------------------------------------
# ToolResult serialisation
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_to_dict_success(self) -> None:
        r = ToolResult(success=True, data={"x": 1}, duration_ms=5.5)
        d = r.to_dict()
        assert d == {
            "success": True,
            "data": {"x": 1},
            "error": None,
            "duration_ms": 5.5,
        }

    def test_to_dict_failure(self) -> None:
        r = ToolResult(success=False, error="oops")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "oops"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_tool_registry_returns_same_instance(self) -> None:
        a = get_tool_registry()
        b = get_tool_registry()
        assert a is b
