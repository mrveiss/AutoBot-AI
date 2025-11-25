# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Type Definitions

Provides strongly-typed definitions to replace generic Any types throughout the codebase.
This module helps ensure type safety, better IDE support, and clearer documentation.
"""

from backend.types.api import (
    APIErrorResponse,
    APIResponse,
    APISuccessResponse,
    PaginatedResponse,
)
from backend.types.common import (
    JSONArray,
    JSONObject,
    JSONPrimitive,
    JSONValue,
    Metadata,
    MetricsDict,
    TimestampStr,
)
from backend.types.mcp import (
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
