# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Type Definitions

Provides strongly-typed definitions to replace generic Any types throughout the codebase.
This module helps ensure type safety, better IDE support, and clearer documentation.
"""

from type_defs.api import (
    APIErrorResponse,
    APIResponse,
    APISuccessResponse,
    PaginatedResponse,
)
from type_defs.common import (
    JSONArray,
    JSONObject,
    JSONPrimitive,
    JSONValue,
    Metadata,
    MetricsDict,
    TimestampStr,
)
from type_defs.mcp import (
    MCPErrorResponse,
    MCPInputSchema,
    MCPSuccessResponse,
    MCPToolDefinition,
    MCPToolResponse,
)

__all__ = [
    # Common types
    "JSONValue",
    "JSONObject",
    "JSONArray",
    "JSONPrimitive",
    "Metadata",
    "MetricsDict",
    "TimestampStr",
    # API types
    "APIResponse",
    "APISuccessResponse",
    "APIErrorResponse",
    "PaginatedResponse",
    # MCP types
    "MCPToolDefinition",
    "MCPToolResponse",
    "MCPSuccessResponse",
    "MCPErrorResponse",
    "MCPInputSchema",
]
