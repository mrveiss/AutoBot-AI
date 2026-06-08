# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tool SDK — unified tool contract for AutoBot (#3018).

Provides the shared abstractions that ToolRegistry, TaskExecutor, and
MCPDispatcher all lack: a declared input schema, a permission level, and
auto-discoverable metadata.

Quick start::

    from tool_sdk import BaseTool, ToolMetadata, ToolPermission, ToolResult
    from tool_sdk import ToolSDKRegistry, get_tool_registry

Public API
----------
BaseTool         — Abstract base class; subclass and implement ``execute()``.
ToolMetadata     — Dataclass carrying name, description, version, permission, tags.
ToolPermission   — Enum: PUBLIC, AUTHENTICATED, ADMIN, SYSTEM.
ToolResult       — Dataclass: success, data, error, duration_ms.
ToolInputError   — Raised by validate_input() on bad input.
ToolSDKRegistry  — Registry: register, get, list_tools, execute, to_openapi_spec.
get_tool_registry — Returns the module-level singleton ToolSDKRegistry.
"""

from tool_sdk.base import (
    BaseTool,
    ToolInputError,
    ToolMetadata,
    ToolPermission,
    ToolResult,
)
from tool_sdk.registry import (
    PermissionDeniedError,
    ToolNotFoundError,
    ToolSDKRegistry,
    get_tool_registry,
)

# Alias for plan-specified name (#3009)
get_tool_sdk_registry = get_tool_registry

__all__ = [
    "BaseTool",
    "ToolInputError",
    "ToolMetadata",
    "ToolPermission",
    "ToolResult",
    "PermissionDeniedError",
    "ToolNotFoundError",
    "ToolSDKRegistry",
    "get_tool_registry",
    "get_tool_sdk_registry",
]
