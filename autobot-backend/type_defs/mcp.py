# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
MCP (Model Context Protocol) Type Definitions for AutoBot

Provides strongly-typed MCP tool and response structures.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from backend.type_defs.common import JSONValue, Metadata
from pydantic import BaseModel, Field

# MCP-specific type aliases
MCPToolName = str
MCPResourceUri = str


class MCPPropertyDefinition(BaseModel):
    """JSON Schema property definition for MCP tools."""

    type: str = Field(..., description="JSON Schema type")
    description: Optional[str] = None
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None
    # Use Any for self-referential fields to avoid Pydantic recursion issues
    items: Optional[Any] = None  # Would be MCPPropertyDefinition
    properties: Optional[Metadata] = None  # Would be Dict[str, MCPPropertyDefinition]
    required: Optional[List[str]] = None


class MCPInputSchema(BaseModel):
    """MCP tool input schema (JSON Schema format)."""

    type: Literal["object"] = "object"
    properties: Dict[str, MCPPropertyDefinition] = Field(default_factory=dict)
    required: List[str] = Field(default_factory=list)
    additionalProperties: bool = False


class MCPToolDefinition(BaseModel):
    """MCP tool definition structure."""

    name: MCPToolName
    description: str
    input_schema: MCPInputSchema = Field(alias="inputSchema")
    category: Optional[str] = None
    tags: Optional[List[str]] = None

    class Config:
        populate_by_name = True


class MCPSuccessResponse(BaseModel):
    """MCP success response structure."""

    success: bool = True
    content: List[Dict[str, JSONValue]] = Field(default_factory=list)
    is_error: bool = Field(False, alias="isError")

    class Config:
        populate_by_name = True


class MCPErrorResponse(BaseModel):
    """MCP error response structure."""

    success: bool = False
    error: str
    error_code: Optional[str] = None
    is_error: bool = Field(True, alias="isError")
    details: Optional[Metadata] = None

    class Config:
        populate_by_name = True


# Union type for MCP tool responses
MCPToolResponse = Union[MCPSuccessResponse, MCPErrorResponse]


class MCPTextContent(BaseModel):
    """MCP text content block."""

    type: Literal["text"] = "text"
    text: str


class MCPImageContent(BaseModel):
    """MCP image content block."""

    type: Literal["image"] = "image"
    data: str  # Base64 encoded
    mime_type: str = Field(alias="mimeType")

    class Config:
        populate_by_name = True


class MCPResourceContent(BaseModel):
    """MCP resource content block."""

    type: Literal["resource"] = "resource"
    uri: MCPResourceUri
    mime_type: Optional[str] = Field(None, alias="mimeType")
    text: Optional[str] = None
    blob: Optional[str] = None  # Base64 encoded

    class Config:
        populate_by_name = True


# Content types that can appear in MCP responses
MCPContent = Union[MCPTextContent, MCPImageContent, MCPResourceContent]


class MCPToolCallRequest(BaseModel):
    """MCP tool call request structure."""

    name: MCPToolName
    arguments: Metadata = Field(default_factory=dict)


class MCPToolCallResult(BaseModel):
    """MCP tool call result structure."""

    tool_name: MCPToolName
    success: bool
    content: List[MCPContent] = Field(default_factory=list)
    execution_time_ms: Optional[float] = None
    is_error: bool = False


class MCPResourceDefinition(BaseModel):
    """MCP resource definition structure."""

    uri: MCPResourceUri
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")

    class Config:
        populate_by_name = True


class MCPPromptDefinition(BaseModel):
    """MCP prompt definition structure."""

    name: str
    description: Optional[str] = None
    arguments: Optional[List[Dict[str, str]]] = None


class MCPCapabilities(BaseModel):
    """MCP server capabilities structure."""

    tools: Optional[List[MCPToolDefinition]] = None
    resources: Optional[List[MCPResourceDefinition]] = None
    prompts: Optional[List[MCPPromptDefinition]] = None


# Note: model_rebuild() removed - using Any for self-referential fields instead
