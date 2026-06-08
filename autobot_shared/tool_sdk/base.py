# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool SDK Base Classes — unified tool contract for AutoBot (#3018).

Provides the shared abstractions that ToolRegistry, TaskExecutor, and
MCPDispatcher all lack: a declared input schema, a permission level, and
auto-discoverable metadata.

All tool implementations should subclass BaseTool, declare ``metadata`` and
``input_schema`` at the class level, and implement ``execute()``.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission model
# ---------------------------------------------------------------------------


class ToolPermission(str, Enum):
    """Access level required to invoke a tool.

    Permissions are ordered from least to most privileged:
        PUBLIC < AUTHENTICATED < ADMIN < SYSTEM

    A caller with a higher-privilege level may always call tools that require
    a lower-privilege level.
    """

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    ADMIN = "admin"
    SYSTEM = "system"

    def allows(self, required: "ToolPermission") -> bool:
        """Return True if this permission level satisfies *required*.

        Args:
            required: The minimum permission the tool demands.

        Returns:
            True when the caller's level is >= the required level.
        """
        order = [
            ToolPermission.PUBLIC,
            ToolPermission.AUTHENTICATED,
            ToolPermission.ADMIN,
            ToolPermission.SYSTEM,
        ]
        try:
            return order.index(self) >= order.index(required)
        except ValueError:
            return False


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass
class ToolMetadata:
    """Declarative metadata for a tool.

    Attached to every BaseTool subclass as a class-level attribute so that
    registries and OpenAPI exporters can inspect it without instantiating the
    tool.
    """

    name: str
    """Unique tool identifier (snake_case)."""

    description: str
    """Human-readable summary shown in LLM function-call payloads."""

    version: str = "1.0.0"
    """Semantic version string (MAJOR.MINOR.PATCH)."""

    permission: ToolPermission = ToolPermission.AUTHENTICATED
    """Minimum caller permission required to execute this tool."""

    tags: List[str] = field(default_factory=list)
    """Organisational tags for filtering / grouping (e.g. ["system", "read"])."""


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Standardised return value from every BaseTool execution.

    Callers should always inspect ``success`` before using ``data``.
    When ``success`` is False the reason is in ``error``.
    """

    success: bool
    """True when the tool completed without an error."""

    data: Any = None
    """Payload produced by the tool on success (structure depends on the tool)."""

    error: str | None = None
    """Human-readable error description when ``success`` is False."""

    duration_ms: float = 0.0
    """Wall-clock execution time in milliseconds."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict suitable for JSON transport."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------


class ToolInputError(ValueError):
    """Raised by ``BaseTool.validate_input()`` when input does not satisfy the schema."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


# ---------------------------------------------------------------------------
# Abstract base tool
# ---------------------------------------------------------------------------


class BaseTool(ABC):
    """Abstract base class for all AutoBot tools.

    Sub-classes **must** set two class-level attributes:

    * ``metadata: ToolMetadata`` — name, description, permission, tags
    * ``input_schema: dict`` — JSON Schema (Draft-07) describing the expected
      input.  The schema is used for validation and OpenAPI export.

    Then implement ``execute(validated_input)``.

    Example::

        class EchoTool(BaseTool):
            metadata = ToolMetadata(
                name="echo",
                description="Returns the input text unchanged.",
                permission=ToolPermission.PUBLIC,
                tags=["utility"],
            )
            input_schema = {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to echo"},
                },
                "required": ["text"],
                "additionalProperties": False,
            }

            async def execute(self, validated_input: dict) -> ToolResult:
                return ToolResult(success=True, data={"text": validated_input["text"]})
    """

    # Sub-classes must override these two class attributes.
    metadata: ToolMetadata
    input_schema: Dict[str, Any]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce that every concrete subclass declares metadata and input_schema."""
        super().__init_subclass__(**kwargs)
        # Skip abstract classes — they still have unresolved abstract methods.
        if getattr(cls, "__abstractmethods__", None):
            return
        missing = [attr for attr in ("metadata", "input_schema") if not hasattr(cls, attr)]
        if missing:
            raise TypeError(f"BaseTool subclass '{cls.__name__}' must define: {', '.join(missing)}")

    def validate_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate *data* against ``self.input_schema``.

        Uses lightweight built-in validation so that ``jsonschema`` is not a
        hard dependency.  The implementation checks:

        * required properties are present
        * no additional properties (when ``additionalProperties`` is False)
        * basic type checking for ``string``, ``integer``, ``number``,
          ``boolean``, ``array``, and ``object``

        Args:
            data: Raw input dict from the caller.

        Returns:
            The validated (and possibly coerced) data dict.

        Raises:
            ToolInputError: When validation fails.
        """
        return _validate_against_schema(data, self.input_schema)

    @abstractmethod
    async def execute(self, validated_input: Dict[str, Any]) -> ToolResult:
        """Execute the tool with pre-validated input.

        Called exclusively by ``ToolSDKRegistry.execute()``, which handles
        input validation and timing automatically.  Do **not** call
        ``validate_input()`` again inside this method.

        Args:
            validated_input: Input dict already validated by ``validate_input()``.

        Returns:
            ToolResult describing the outcome.
        """

    def to_openapi_schema(self) -> Dict[str, Any]:
        """Return an OpenAPI-compatible tool definition dict.

        The output format matches the LLM function-calling convention used by
        ``MCPDispatcher.get_tool_definitions()`` so callers have a single
        consistent format.

        Returns:
            Dict with keys: name, description, version, permission, tags,
            parameters (the tool's input_schema).
        """
        return {
            "name": self.metadata.name,
            "description": self.metadata.description,
            "version": self.metadata.version,
            "permission": self.metadata.permission.value,
            "tags": list(self.metadata.tags),
            "parameters": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Internal schema validator
# ---------------------------------------------------------------------------

_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_type(data: Any, schema_type: str, path: str) -> None:
    """Raise ToolInputError if *data* does not match *schema_type* (#3018).

    Args:
        data: Value to check.
        schema_type: JSON Schema primitive type string.
        path: Dot-notation path used in error messages.
    """
    if not schema_type or schema_type == "null":
        return
    expected = _TYPE_MAP.get(schema_type)
    if expected and not isinstance(data, expected):
        label = path or "input"
        raise ToolInputError(
            f"'{label}' must be of type {schema_type}, got {type(data).__name__}",
            field=path,
        )


def _check_string_constraints(data: str, schema: Dict[str, Any], path: str) -> None:
    """Validate minLength / maxLength for string values (#3018).

    Args:
        data: String value already confirmed to be str.
        schema: The property's JSON Schema dict.
        path: Dot-notation path used in error messages.
    """
    label = path or "input"
    min_len = schema.get("minLength")
    max_len = schema.get("maxLength")
    if min_len is not None and len(data) < min_len:
        raise ToolInputError(
            f"'{label}' must be at least {min_len} characters, got {len(data)}",
            field=path,
        )
    if max_len is not None and len(data) > max_len:
        raise ToolInputError(
            f"'{label}' must be at most {max_len} characters, got {len(data)}",
            field=path,
        )


def _check_numeric_constraints(data: Any, schema: Dict[str, Any], path: str) -> None:
    """Validate minimum / maximum for numeric values (#3018).

    Args:
        data: Numeric value already confirmed to be int or float.
        schema: The property's JSON Schema dict.
        path: Dot-notation path used in error messages.
    """
    label = path or "input"
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if minimum is not None and data < minimum:
        raise ToolInputError(f"'{label}' must be >= {minimum}, got {data}", field=path)
    if maximum is not None and data > maximum:
        raise ToolInputError(f"'{label}' must be <= {maximum}, got {data}", field=path)


def _check_object_properties(data: dict, schema: Dict[str, Any], path: str) -> None:
    """Validate required fields, additionalProperties, and recurse into properties (#3018).

    Args:
        data: Dict value already confirmed to be dict.
        schema: The object's JSON Schema dict.
        path: Dot-notation path used in error messages.
    """
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional_allowed = schema.get("additionalProperties", True)

    for req_field in required:
        if req_field not in data:
            label = f"{path}.{req_field}" if path else req_field
            raise ToolInputError(f"Required field '{label}' is missing", field=label)

    if additional_allowed is False:
        for key in data:
            if key not in properties:
                label = f"{path}.{key}" if path else key
                raise ToolInputError(
                    f"Unexpected field '{label}' (additionalProperties is false)",
                    field=label,
                )

    for prop_name, prop_schema in properties.items():
        if prop_name in data:
            child_path = f"{path}.{prop_name}" if path else prop_name
            _validate_against_schema(data[prop_name], prop_schema, child_path)


def _validate_against_schema(
    data: Any,
    schema: Dict[str, Any],
    path: str = "",
) -> Any:
    """Recursively validate *data* against a JSON Schema subset (#3018).

    Delegates each constraint category to a dedicated helper:
    _check_type, _check_string_constraints, _check_numeric_constraints,
    _check_object_properties.

    Supports: type, required, properties, additionalProperties, items,
    minimum, maximum, minLength, maxLength, enum.

    Args:
        data: Value to validate.
        schema: JSON Schema dict (Draft-07 subset).
        path: Dot-notation path for error messages.

    Returns:
        The validated data (unchanged; coercion is not performed).

    Raises:
        ToolInputError: On any validation failure.
    """
    if not isinstance(schema, dict):
        return data

    schema_type = schema.get("type")
    _check_type(data, schema_type or "", path)

    enum_values = schema.get("enum")
    if enum_values is not None and data not in enum_values:
        label = path or "input"
        raise ToolInputError(
            f"'{label}' must be one of {enum_values!r}, got {data!r}",
            field=path,
        )

    if schema_type == "string" and isinstance(data, str):
        _check_string_constraints(data, schema, path)

    if schema_type in ("integer", "number") and isinstance(data, (int, float)):
        _check_numeric_constraints(data, schema, path)

    if schema_type == "object" and isinstance(data, dict):
        _check_object_properties(data, schema, path)

    if schema_type == "array" and isinstance(data, list):
        items_schema = schema.get("items")
        if items_schema:
            for idx, item in enumerate(data):
                _validate_against_schema(item, items_schema, f"{path}[{idx}]")

    return data


# ---------------------------------------------------------------------------
# Convenience: time a coroutine and wrap in ToolResult
# ---------------------------------------------------------------------------


async def _timed_execute(tool: BaseTool, validated_input: Dict[str, Any]) -> ToolResult:
    """Call ``tool.execute()`` and attach wall-clock timing to the result.

    Args:
        tool: The tool instance to execute.
        validated_input: Already-validated input dict.

    Returns:
        ToolResult with ``duration_ms`` populated.
    """
    start = time.monotonic()
    try:
        result = await tool.execute(validated_input)
    except Exception as exc:  # noqa: BLE001 — catch-all intentional here
        duration = (time.monotonic() - start) * 1000
        logger.error(
            "Tool '%s' raised an unhandled exception: %s",
            tool.metadata.name,
            exc,
            exc_info=True,
        )
        return ToolResult(
            success=False,
            error=f"Unhandled tool error: {exc}",
            duration_ms=round(duration, 2),
        )
    duration = (time.monotonic() - start) * 1000
    result.duration_ms = round(duration, 2)
    return result
