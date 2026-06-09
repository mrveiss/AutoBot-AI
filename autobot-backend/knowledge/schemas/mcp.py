# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response schemas for MCP bridge and RAG feedback endpoints (Issue #5317 batch 4c)."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class McpToolsResponse(BaseModel):
    """Shape returned by GET /mcp/tools — list of MCPTool definitions."""

    model_config = ConfigDict(extra="allow")

    name: str
    description: str
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class McpSearchResult(BaseModel):
    """Single result entry from a knowledge base search."""

    model_config = ConfigDict(extra="allow")

    content: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: str = "unknown"


class McpSearchResponse(BaseModel):
    """Shape returned by POST /mcp/search_knowledge_base."""

    model_config = ConfigDict(extra="allow")

    success: bool
    results: List[Dict[str, Any]] = Field(default_factory=list)
    query: str = ""
    count: int = 0
    error: str | None = None


class McpAddDocumentResponse(BaseModel):
    """Shape returned by POST /mcp/add_to_knowledge_base."""

    model_config = ConfigDict(extra="allow")

    success: bool
    document_id: str | None = None
    message: str | None = None
    error: str | None = None


class McpKnowledgeStatsResponse(BaseModel):
    """Shape returned by POST /mcp/get_knowledge_stats."""

    model_config = ConfigDict(extra="allow")

    success: bool
    stats: Dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class McpSummarizeTopicResponse(BaseModel):
    """Shape returned by POST /mcp/summarize_knowledge_topic."""

    model_config = ConfigDict(extra="allow")

    success: bool
    summary: str = ""
    topic: str | None = None
    source_count: int = 0
    error: str | None = None


class McpVectorSimilarityResponse(BaseModel):
    """Shape returned by POST /mcp/vector_similarity_search."""

    model_config = ConfigDict(extra="allow")

    success: bool
    results: List[Dict[str, Any]] = Field(default_factory=list)
    query: str | None = None
    threshold: float | None = None
    error: str | None = None


class McpQaChainResponse(BaseModel):
    """Shape returned by POST /mcp/langchain_qa_chain."""

    model_config = ConfigDict(extra="allow")

    success: bool
    answer: str = ""
    question: str | None = None
    sources: List[str] = Field(default_factory=list)
    error: str | None = None


class McpRedisVectorOpsResponse(BaseModel):
    """Shape returned by POST /mcp/redis_vector_operations."""

    model_config = ConfigDict(extra="allow")

    success: bool
    operation: str | None = None
    data: Dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None


class McpSchemaBackends(BaseModel):
    """Backends sub-object in the MCP schema response."""

    model_config = ConfigDict(extra="allow")

    langchain: str = ""
    llama_index: str = ""
    redis: str = ""


class McpSchemaResponse(BaseModel):
    """Shape returned by GET /mcp/schema."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    version: str = ""
    description: str = ""
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    backends: Dict[str, str] = Field(default_factory=dict)


class McpHealthResponse(BaseModel):
    """Shape returned by GET /mcp/health."""

    model_config = ConfigDict(extra="allow")

    status: str
    knowledge_base_initialized: bool = False
    vector_store_connected: bool = False
    error: str | None = None


class RagFeedbackResponse(BaseModel):
    """Shape returned by POST /rag-feedback."""

    model_config = ConfigDict(extra="allow")

    status: str
    stream_key: str | None = None
    decision: str | None = None
    reason: str | None = None


class KnowledgeSearchRequest(BaseModel):
    """Request body for POST /mcp/search_knowledge_base."""

    query: str = Field(..., description="Search query")
    top_k: int = Field(5, description="Number of results to return")
    filters: Dict[str, Any] | None = Field(None, description="Optional filters")


class DocumentAddRequest(BaseModel):
    """Request body for POST /mcp/add_to_knowledge_base."""

    content: str = Field(..., description="Document content")
    metadata: Dict[str, Any] | None = Field(None, description="Document metadata")
    source: str | None = Field(None, description="Document source")


class KnowledgeStatsRequest(BaseModel):
    """Request body for POST /mcp/get_knowledge_stats."""

    include_details: bool = Field(False, description="Include detailed statistics")
