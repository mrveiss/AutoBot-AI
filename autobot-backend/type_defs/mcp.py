# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP (Model Context Protocol) Type Definitions for AutoBot

Provides strongly-typed MCP tool and response structures.
"""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from type_defs.common import JSONValue, Metadata

# MCP-specific type aliases
MCPToolName = str
MCPResourceUri = str


class MCPPropertyDefinition(BaseModel):
    """JSON Schema property definition for MCP tools."""

    type: str = Field(..., description="JSON Schema type")
    description: str | None = None
    default: Any | None = None
    enum: List[Any] | None = None
    # Use Any for self-referential fields to avoid Pydantic recursion issues
    items: Any | None = None  # Would be MCPPropertyDefinition
    properties: Metadata | None = None  # Would be Dict[str, MCPPropertyDefinition]
    required: List[str] | None = None


class MCPInputSchema(BaseModel):
    """MCP tool input schema (JSON Schema format)."""

    type: Literal["object"] = "object"
    properties: Dict[str, MCPPropertyDefinition] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)
    additionalProperties: bool = False


class MCPToolDefinition(BaseModel):
    """MCP tool definition structure."""

    model_config = ConfigDict(populate_by_name=True)

    name: MCPToolName
    description: str
    input_schema: MCPInputSchema = Field(alias="inputSchema")
    category: str | None = None
    tags: List[str] | None = None


class MCPSuccessResponse(BaseModel):
    """MCP success response structure."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool = True
    content: List[Dict[str, JSONValue]] = Field(default_factory=list)
    is_error: bool = Field(False, alias="isError")


class MCPErrorResponse(BaseModel):
    """MCP error response structure."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool = False
    error: str
    error_code: str | None = None
    is_error: bool = Field(True, alias="isError")
    details: Metadata | None = None


# Union type for MCP tool responses
MCPToolResponse = MCPSuccessResponse | MCPErrorResponse


class MCPTextContent(BaseModel):
    """MCP text content block."""

    type: Literal["text"] = "text"
    text: str


class MCPImageContent(BaseModel):
    """MCP image content block."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["image"] = "image"
    data: str  # Base64 encoded
    mime_type: str = Field(alias="mimeType")


class MCPResourceContent(BaseModel):
    """MCP resource content block."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["resource"] = "resource"
    uri: MCPResourceUri
    mime_type: str | None = Field(None, alias="mimeType")
    text: str | None = None
    blob: str | None = None  # Base64 encoded


# Content types that can appear in MCP responses
MCPContent = MCPTextContent | MCPImageContent | MCPResourceContent


class MCPToolCallRequest(BaseModel):
    """MCP tool call request structure."""

    name: MCPToolName
    arguments: Metadata = Field(default_factory=dict)


class MCPToolCallResult(BaseModel):
    """MCP tool call result structure."""

    tool_name: MCPToolName
    success: bool
    content: List[MCPContent] = Field(default_factory=list)
    execution_time_ms: float | None = None
    is_error: bool = False


class MCPResourceDefinition(BaseModel):
    """MCP resource definition structure."""

    model_config = ConfigDict(populate_by_name=True)

    uri: MCPResourceUri
    name: str
    description: str | None = None
    mime_type: str | None = Field(None, alias="mimeType")


class MCPPromptDefinition(BaseModel):
    """MCP prompt definition structure."""

    name: str
    description: str | None = None
    arguments: List[Dict[str, str]] | None = None


class MCPCapabilities(BaseModel):
    """MCP server capabilities structure."""

    tools: List[MCPToolDefinition] | None = None
    resources: List[MCPResourceDefinition] | None = None
    prompts: List[MCPPromptDefinition] | None = None


# Note: model_rebuild() removed - using Any for self-referential fields instead
