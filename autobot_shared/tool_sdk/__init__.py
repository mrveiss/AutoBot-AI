# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tool SDK — unified tool contract for AutoBot (#3018).

Provides the shared abstractions that ToolRegistry, TaskExecutor, and
MCPDispatcher all lack: a declared input schema, a permission level, and
auto-discoverable metadata.

Quick start::

    from autobot_shared.tool_sdk import BaseTool, ToolMetadata, ToolPermission, ToolResult
    from autobot_shared.tool_sdk import ToolSDKRegistry, get_tool_registry

Public API
----------
BaseTool         — Abstract base class; subclass and implement ``execute()``.
ToolMetadata     — Dataclass carrying name, description, version, permission, tags.
ToolPermission   — Enum: PUBLIC, AUTHENTICATED, ADMIN, SYSTEM.
ToolResult       — Dataclass: success, data, error, duration_ms.
ToolInputError   — Raised by validate_input() on bad input.
ToolSDKRegistry  — Registry: register, get, list_tools, execute, to_openapi_spec.
get_tool_registry — Returns the module-level singleton ToolSDKRegistry.

Note (#14373): the internal imports below are relative (``from .base import``)
rather than a bare ``from tool_sdk.base import``. ``get_tool_registry()``
returns a module-level singleton stored on this package's ``registry``
submodule; if that submodule were ever loaded under a second identity (e.g.
a bare top-level ``tool_sdk.registry`` alongside this package's
``autobot_shared.tool_sdk.registry``), it would carry its own, independently
empty, registry instance. Only ``autobot_shared.tool_sdk`` is a supported
import path — a bare ``tool_sdk`` alias is deliberately not provided.
"""

from .base import (
    BaseTool,
    ToolInputError,
    ToolMetadata,
    ToolPermission,
    ToolResult,
)
from .registry import (
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
