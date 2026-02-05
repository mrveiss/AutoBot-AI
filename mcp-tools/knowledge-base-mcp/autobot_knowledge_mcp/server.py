# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Knowledge Base MCP Server

True MCP server implementation using stdio transport for direct
integration with Claude and other MCP-compatible clients.

Usage:
    # Run directly
    python -m autobot_knowledge_mcp.server

    # Or via entry point
    autobot-knowledge-mcp

Configuration (environment variables):
    AUTOBOT_BACKEND_HOST: Backend API host (default: 172.16.168.20)
    AUTOBOT_BACKEND_PORT: Backend API port (default: 8001)
    AUTOBOT_KB_TIMEOUT: Request timeout in seconds (default: 30)
"""

import asyncio
import logging
import os
import sys
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field

# Configure logging to stderr (stdout is for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("autobot-knowledge-mcp")

# Configuration from environment
BACKEND_HOST = os.getenv("AUTOBOT_BACKEND_HOST", "172.16.168.20")
BACKEND_PORT = os.getenv("AUTOBOT_BACKEND_PORT", "8001")
KB_TIMEOUT = int(os.getenv("AUTOBOT_KB_TIMEOUT", "30"))
BASE_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/knowledge"


# =============================================================================
# Request/Response Models
# =============================================================================


class SearchRequest(BaseModel):
    """Search request parameters."""

    query: str = Field(..., description="Search query text")
    top_k: int = Field(5, description="Number of results to return", ge=1, le=50)
    threshold: float = Field(
        0.0, description="Minimum similarity threshold", ge=0.0, le=1.0
    )


class AddDocumentRequest(BaseModel):
    """Add document request parameters."""

    content: str = Field(..., description="Document content to add")
    source: str = Field("mcp-client", description="Source identifier")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata"
    )


class SummarizeRequest(BaseModel):
    """Summarize topic request parameters."""

    topic: str = Field(..., description="Topic to summarize")
    max_length: int = Field(500, description="Maximum summary length in tokens")


# =============================================================================
# MCP Server
# =============================================================================


class KnowledgeBaseMCPServer:
    """
    MCP server for AutoBot knowledge base.

    Provides tools for semantic search, document addition, and
    knowledge base management via the Model Context Protocol.
    """

    def __init__(self):
        """Initialize the MCP server."""
        self.server = Server("autobot-knowledge-base")
        self.http_client: httpx.AsyncClient | None = None
        self._setup_handlers()

    def _setup_handlers(self):
        """Set up MCP request handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """Return the list of available tools."""
            return [
                self._get_search_knowledge_tool(),
                self._get_add_knowledge_tool(),
                self._get_knowledge_stats_tool(),
                self._get_summarize_topic_tool(),
                self._get_vector_search_tool(),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            try:
                return await self._dispatch_tool_call(name, arguments)
            except httpx.RequestError as e:
                logger.error("HTTP request failed: %s", e)
                return [
                    TextContent(
                        type="text",
                        text=f"Error: Failed to connect to AutoBot backend at {BASE_URL}. Is it running?",
                    )
                ]
            except Exception as e:
                logger.error("Tool execution failed: %s", e)
                return [
                    TextContent(
                        type="text",
                        text=f"Error executing {name}: {str(e)}",
                    )
                ]

    async def _dispatch_tool_call(
        self, name: str, arguments: dict[str, Any]
    ) -> list[TextContent]:
        """Dispatch tool call to appropriate handler. Helper for _setup_handlers (Issue #665)."""
        handlers = {
            "search_knowledge": self._search_knowledge,
            "add_knowledge": self._add_knowledge,
            "knowledge_stats": self._knowledge_stats,
            "summarize_topic": self._summarize_topic,
            "vector_search": self._vector_search,
        }
        handler = handlers.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return await handler(arguments)

    def _get_search_knowledge_tool(self) -> Tool:
        """Return search_knowledge Tool definition. Helper for _setup_handlers (Issue #665)."""
        return Tool(
            name="search_knowledge",
            description=(
                "Search AutoBot's knowledge base using semantic similarity. "
                "Returns relevant documents based on the query. Use this to find "
                "information about AutoBot's configuration, architecture, APIs, "
                "or any previously stored knowledge."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query - describe what you're looking for",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (1-50)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Minimum similarity score (0.0-1.0)",
                        "default": 0.0,
                        "minimum": 0.0,
                        "maximum": 1.0,
                    },
                },
                "required": ["query"],
            },
        )

    def _get_add_knowledge_tool(self) -> Tool:
        """Return add_knowledge Tool definition. Helper for _setup_handlers (Issue #665)."""
        return Tool(
            name="add_knowledge",
            description=(
                "Add new information to AutoBot's knowledge base. "
                "The content will be vectorized and stored for future retrieval. "
                "Use this to store important findings, decisions, or documentation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The content to add to the knowledge base",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source identifier (e.g., 'user', 'research', 'documentation')",
                        "default": "mcp-client",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional metadata (category, tags, etc.)",
                        "additionalProperties": True,
                    },
                },
                "required": ["content"],
            },
        )

    def _get_knowledge_stats_tool(self) -> Tool:
        """Return knowledge_stats Tool definition. Helper for _setup_handlers (Issue #665)."""
        return Tool(
            name="knowledge_stats",
            description=(
                "Get statistics about the knowledge base including document count, "
                "index information, and storage details."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_details": {
                        "type": "boolean",
                        "description": "Include detailed statistics",
                        "default": False,
                    },
                },
            },
        )

    def _get_summarize_topic_tool(self) -> Tool:
        """Return summarize_topic Tool definition. Helper for _setup_handlers (Issue #665)."""
        return Tool(
            name="summarize_topic",
            description=(
                "Get a summary of knowledge on a specific topic. "
                "Searches for relevant documents and synthesizes a summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic to summarize",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum summary length in tokens",
                        "default": 500,
                    },
                },
                "required": ["topic"],
            },
        )

    def _get_vector_search_tool(self) -> Tool:
        """Return vector_search Tool definition. Helper for _setup_handlers (Issue #665)."""
        return Tool(
            name="vector_search",
            description=(
                "Perform direct vector similarity search with threshold filtering. "
                "More precise than semantic search for finding exact matches."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query text to embed and search",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 10,
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Minimum similarity threshold (0.0-1.0)",
                        "default": 0.7,
                    },
                },
                "required": ["query"],
            },
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.http_client is None or self.http_client.is_closed:
            self.http_client = httpx.AsyncClient(timeout=KB_TIMEOUT)
        return self.http_client

    async def _search_knowledge(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute knowledge base search."""
        request = SearchRequest(**arguments)
        client = await self._get_client()

        response = await client.post(
            f"{BASE_URL}/mcp/search_knowledge_base",
            json={
                "query": request.query,
                "top_k": request.top_k,
                "filters": {"threshold": request.threshold}
                if request.threshold > 0
                else None,
            },
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            return [
                TextContent(
                    type="text",
                    text=f"Search failed: {data.get('error', 'Unknown error')}",
                )
            ]

        results = data.get("results", [])
        if not results:
            return [
                TextContent(
                    type="text",
                    text=f"No results found for query: '{request.query}'",
                )
            ]

        # Format results
        formatted = [f"Found {len(results)} results for '{request.query}':\n"]
        for i, result in enumerate(results, 1):
            content = result.get("content", "")[:500]
            score = result.get("score", 0)
            source = result.get("source", "unknown")
            formatted.append(
                f"\n---\n**Result {i}** (score: {score:.3f}, source: {source})\n{content}"
            )

        return [TextContent(type="text", text="".join(formatted))]

    async def _add_knowledge(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Add document to knowledge base."""
        request = AddDocumentRequest(**arguments)
        client = await self._get_client()

        response = await client.post(
            f"{BASE_URL}/mcp/add_to_knowledge_base",
            json={
                "content": request.content,
                "source": request.source,
                "metadata": request.metadata,
            },
        )
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            doc_id = data.get("document_id", "unknown")
            return [
                TextContent(
                    type="text",
                    text=f"Successfully added document to knowledge base.\nDocument ID: {doc_id}",
                )
            ]
        else:
            return [
                TextContent(
                    type="text",
                    text=f"Failed to add document: {data.get('error', 'Unknown error')}",
                )
            ]

    async def _knowledge_stats(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Get knowledge base statistics."""
        include_details = arguments.get("include_details", False)
        client = await self._get_client()

        response = await client.post(
            f"{BASE_URL}/mcp/get_knowledge_stats",
            json={"include_details": include_details},
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            return [
                TextContent(
                    type="text",
                    text=f"Failed to get stats: {data.get('error', 'Unknown error')}",
                )
            ]

        stats = data.get("stats", {})
        lines = ["**Knowledge Base Statistics**\n"]
        for key, value in stats.items():
            lines.append(f"- {key}: {value}")

        return [TextContent(type="text", text="\n".join(lines))]

    async def _summarize_topic(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Summarize knowledge on a topic."""
        request = SummarizeRequest(**arguments)
        client = await self._get_client()

        response = await client.post(
            f"{BASE_URL}/mcp/summarize_knowledge_topic",
            json={
                "topic": request.topic,
                "max_length": request.max_length,
            },
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            return [
                TextContent(
                    type="text",
                    text=f"Failed to summarize: {data.get('error', 'Unknown error')}",
                )
            ]

        summary = data.get("summary", "No summary available")
        source_count = data.get("source_count", 0)

        return [
            TextContent(
                type="text",
                text=f"**Summary of '{request.topic}'** (based on {source_count} sources)\n\n{summary}",
            )
        ]

    async def _vector_search(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Perform vector similarity search."""
        query = arguments.get("query", "")
        top_k = arguments.get("top_k", 10)
        threshold = arguments.get("threshold", 0.7)

        client = await self._get_client()

        response = await client.post(
            f"{BASE_URL}/mcp/vector_similarity_search",
            json={
                "query": query,
                "top_k": top_k,
                "threshold": threshold,
            },
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success"):
            return [
                TextContent(
                    type="text",
                    text=f"Vector search failed: {data.get('error', 'Unknown error')}",
                )
            ]

        results = data.get("results", [])
        if not results:
            return [
                TextContent(
                    type="text",
                    text=f"No vectors found above threshold {threshold} for query: '{query}'",
                )
            ]

        formatted = [f"Found {len(results)} vectors above threshold {threshold}:\n"]
        for i, result in enumerate(results, 1):
            content = result.get("content", "")[:300]
            score = result.get("score", 0)
            formatted.append(f"\n---\n**{i}.** (similarity: {score:.3f})\n{content}")

        return [TextContent(type="text", text="".join(formatted))]

    async def run(self):
        """Run the MCP server."""
        logger.info("Starting AutoBot Knowledge Base MCP Server")
        logger.info("Backend URL: %s", BASE_URL)

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )

        # Cleanup
        if self.http_client:
            await self.http_client.aclose()


def main():
    """Main entry point."""
    server = KnowledgeBaseMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
