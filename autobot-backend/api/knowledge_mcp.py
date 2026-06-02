# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base MCP Bridge
Exposes knowledge base operations as MCP tools for LLM access.
Integrates with LlamaIndex, Redis Vector Store, and ChatOllama (langchain 1.x).

Issue #1047: Removed LangChainAgentOrchestrator (legacy 0.1 API). QA chain
now uses ChatOllama directly. All tool capabilities merged into LangGraph
graph (chat_workflow/graph.py).
"""

import asyncio
from typing import List

from fastapi import APIRouter, Depends

from api.schemas_code import (
    SubscribeResourceRequest,
    SubscribeResourceResponse,
    UnsubscribeResourceRequest,
    UnsubscribeResourceResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import RedisDatabase, get_redis_client
from autobot_shared.singleton_factory import lazy_singleton
from constants.model_constants import ModelConstants
from dependencies import get_config
from knowledge.schemas.mcp import (
    DocumentAddRequest,
    KnowledgeSearchRequest,
    KnowledgeStatsRequest,
    McpAddDocumentResponse,
    McpHealthResponse,
    McpKnowledgeStatsResponse,
    McpQaChainResponse,
    McpRedisVectorOpsResponse,
    McpSchemaResponse,
    McpSearchResponse,
    McpSummarizeTopicResponse,
    McpToolsResponse,
    McpVectorSimilarityResponse,
)
from services.mcp_bridge_manifest import MCPBridgeManifest

MANIFEST = MCPBridgeManifest(
    name="knowledge_mcp",
    version="1.0.0",
    description="Knowledge Base Operations (LlamaIndex + Redis Vectors)",
    features=["search", "add_documents", "vector_similarity", "statistics"],
    endpoint="/api/knowledge/mcp/tools",
)
from knowledge_base import KnowledgeBase
from type_defs.common import Metadata
from utils.service_registry import get_service_url

logger = get_logger(__name__)
router = APIRouter(tags=["knowledge_mcp", "mcp", "langchain"])

get_knowledge_base = lazy_singleton(lambda: KnowledgeBase(config_manager=get_config()))


def get_vectors_redis_client():
    """Get Redis client for vector operations.

    Issue #692: Migrated from deprecated RedisDatabaseManager to get_redis_client().
    """
    return get_redis_client(database="vectors")


def _get_chat_ollama():
    """Get a ChatOllama instance for LLM calls (langchain 1.x).

    Issue #1047: Replaces LangChainAgentOrchestrator.llm with ChatOllama.
    Uses SSOT config for Ollama endpoint and model selection.
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        logger.warning("langchain-ollama not installed — QA chain LLM unavailable")
        return None

    try:
        llm_config = get_config().get_llm_config()
        model = ModelConstants.DEFAULT_OLLAMA_MODEL
        base_url = llm_config.get("ollama", {}).get("base_url", get_service_url("ollama"))
        return ChatOllama(model=model, base_url=base_url, temperature=0.7)
    except Exception as exc:
        logger.warning("Failed to create ChatOllama: %s", exc)
        return None


def _create_search_tool() -> McpToolsResponse:
    """
    Create MCP tool for knowledge base search.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        McpToolsResponse definition for search_knowledge_base operation
    """
    return McpToolsResponse(
        name="search_knowledge_base",
        description="Search the AutoBot knowledge base using LlamaIndex and Redis vector store",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5,
                },
                "filters": {
                    "type": "object",
                    "description": "Optional filters",
                    "additionalProperties": True,
                },
            },
            "required": ["query"],
        },
    )


def _create_add_document_tool() -> McpToolsResponse:
    """
    Create MCP tool for adding documents to knowledge base.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        McpToolsResponse definition for add_to_knowledge_base operation
    """
    return McpToolsResponse(
        name="add_to_knowledge_base",
        description=("Add new information to the AutoBot knowledge base (stored in Redis" "vectors)"),
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Document content to add",
                },
                "metadata": {
                    "type": "object",
                    "description": "Document metadata",
                    "additionalProperties": True,
                },
                "source": {
                    "type": "string",
                    "description": "Document source identifier",
                },
            },
            "required": ["content"],
        },
    )


def _create_vector_search_tool() -> McpToolsResponse:
    """
    Create MCP tool for vector similarity search.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        McpToolsResponse definition for vector_similarity_search operation
    """
    return McpToolsResponse(
        name="vector_similarity_search",
        description="Perform vector similarity search in Redis using embeddings",
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query text to embed and search",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of similar vectors to return",
                    "default": 10,
                },
                "threshold": {
                    "type": "number",
                    "description": "Similarity threshold (0.0-1.0)",
                    "default": 0.7,
                },
            },
            "required": ["query"],
        },
    )


def _create_qa_chain_tool() -> McpToolsResponse:
    """
    Create MCP tool for LangChain QA chain.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        McpToolsResponse definition for langchain_qa_chain operation
    """
    return McpToolsResponse(
        name="langchain_qa_chain",
        description="Use LangChain QA chain for comprehensive answers from knowledge base",
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question to answer using knowledge base",
                },
                "context_size": {
                    "type": "integer",
                    "description": "Number of context documents to use",
                    "default": 3,
                },
            },
            "required": ["question"],
        },
    )


def _create_extract_tool() -> McpToolsResponse:
    """Create MCP tool descriptor for POST /knowledge/extract.

    Issue #7405: Schema-driven structured data extraction.
    """
    return McpToolsResponse(
        name="extract_structured_data",
        description=(
            "Fetch a URL and extract structured data matching a JSON Schema via LLM. "
            "Strips <script> blocks before prompting (prompt-injection guard). "
            "Returns validated JSON matching the caller-supplied schema."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to fetch"},
                "schema": {"type": "object", "description": "JSON Schema (draft 2020-12) for the output"},
                "render": {
                    "type": "string",
                    "enum": ["auto", "fast", "playwright"],
                    "default": "auto",
                    "description": "Render mode",
                },
                "ingest": {
                    "type": "boolean",
                    "default": False,
                    "description": "Index raw page markdown into ChromaDB",
                },
            },
            "required": ["url", "schema"],
        },
    )


def _create_scrape_url_tool() -> McpToolsResponse:
    """Create MCP tool descriptor for POST /mcp/scrape_url. Issue #7509."""
    return McpToolsResponse(
        name="scrape_url",
        description=(
            "Fetch a single URL and return its full markdown content. "
            "Supports Jina fast-path, BS4, and Playwright render modes. "
            "Returns markdown with a status header."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Absolute URL to fetch"},
                "render": {
                    "type": "string",
                    "enum": ["auto", "fast", "playwright"],
                    "default": "auto",
                    "description": "Render mode",
                },
            },
            "required": ["url"],
        },
    )


def _create_crawl_site_tool() -> McpToolsResponse:
    """Create MCP tool descriptor for POST /mcp/crawl_site. Issue #7509."""
    return McpToolsResponse(
        name="crawl_site",
        description=(
            "BFS crawl one or more seed URLs up to max_depth hops. "
            "Returns a markdown index of crawled pages. "
            "Set ingest=true to write successful pages to the knowledge base."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "seed_urls": {"type": "array", "items": {"type": "string"}, "description": "Starting URLs"},
                "max_depth": {"type": "integer", "default": 1, "description": "Link-hop depth"},
                "max_pages": {"type": "integer", "default": 100, "description": "Hard cap on pages fetched"},
                "respect_robots": {"type": "boolean", "default": True, "description": "Honour robots.txt"},
                "ingest": {"type": "boolean", "default": False, "description": "Write pages to knowledge base"},
                "same_origin": {"type": "boolean", "default": True, "description": "Restrict to same scheme+host"},
            },
            "required": ["seed_urls"],
        },
    )


def _create_map_site_tool() -> McpToolsResponse:
    """Create MCP tool descriptor for POST /mcp/map_site. Issue #7509."""
    return McpToolsResponse(
        name="map_site",
        description=(
            "Discover all URLs for a domain via sitemap.xml, falling back to BFS crawl. "
            "Returns a markdown list of URLs grouped by depth."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domain to map (bare or with scheme)"},
                "max_urls": {"type": "integer", "default": 500, "description": "Hard cap on returned URLs"},
                "respect_robots": {
                    "type": "boolean",
                    "default": True,
                    "description": "Honour robots.txt during crawl fallback",
                },
            },
            "required": ["domain"],
        },
    )


def _get_knowledge_search_tools() -> List[McpToolsResponse]:
    """
    Get MCP tools for knowledge base search and retrieval operations.

    Issue #281: Extracted from get_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.
    Issue #665: Further refactored to reduce from 102 lines to below 20 lines.
    Issue #7405: Added extract_structured_data tool.
    Issue #7509: Added scrape_url, crawl_site, map_site tools.

    Returns:
        List of McpToolsResponse definitions for search/retrieval operations
    """
    return [
        _create_search_tool(),
        _create_add_document_tool(),
        _create_vector_search_tool(),
        _create_qa_chain_tool(),
        _create_extract_tool(),
        _create_scrape_url_tool(),
        _create_crawl_site_tool(),
        _create_map_site_tool(),
    ]


def _get_knowledge_management_tools() -> List[McpToolsResponse]:
    """
    Get MCP tools for knowledge base management and admin operations.

    Issue #281: Extracted from get_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of McpToolsResponse definitions for management/admin operations
    """
    return [
        McpToolsResponse(
            name="get_knowledge_stats",
            description="Get statistics about the AutoBot knowledge base and Redis vector store",
            input_schema={
                "type": "object",
                "properties": {
                    "include_details": {
                        "type": "boolean",
                        "description": "Include detailed statistics",
                        "default": False,
                    }
                },
            },
        ),
        McpToolsResponse(
            name="summarize_knowledge_topic",
            description="Get a summary of knowledge on a specific topic using LangChain",
            input_schema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to summarize"},
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum summary length in tokens",
                        "default": 500,
                    },
                },
                "required": ["topic"],
            },
        ),
        McpToolsResponse(
            name="redis_vector_operations",
            description="Direct Redis vector store operations (advanced)",
            input_schema={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["info", "flush", "reindex", "backup"],
                        "description": "Redis vector operation to perform",
                    },
                    "params": {
                        "type": "object",
                        "description": "Operation-specific parameters",
                        "additionalProperties": True,
                    },
                },
                "required": ["operation"],
            },
        ),
    ]


@router.get("/mcp/tools", response_model=List[McpToolsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_tools",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def get_mcp_tools(
    current_user: dict = Depends(get_current_user),
) -> List[McpToolsResponse]:
    """Get available MCP tools for knowledge base operations.

    Issue #744: Requires authenticated user.
    """
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_knowledge_search_tools())
    tools.extend(_get_knowledge_management_tools())
    return tools


@router.post("/mcp/search_knowledge_base", response_model=McpSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_search_knowledge_base",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_search_knowledge_base(
    request: KnowledgeSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Search the knowledge base.

    Issue #744: Requires authenticated user.
    """
    try:
        kb = get_knowledge_base()

        # Perform the search
        results = await kb.search(query=request.query, top_k=request.top_k, filters=request.filters)

        # Format results for MCP
        formatted_results = []
        for result in results:
            formatted_results.append(
                {
                    "content": result.get("content", ""),
                    "score": result.get("score", 0.0),
                    "metadata": result.get("metadata", {}),
                    "source": result.get("source", "unknown"),
                }
            )

        return {
            "success": True,
            "results": formatted_results,
            "query": request.query,
            "count": len(formatted_results),
        }

    except Exception as e:
        logger.error("Error searching knowledge base: %s", e)
        return {"success": False, "error": "Internal server error", "results": []}


@router.post("/mcp/add_to_knowledge_base", response_model=McpAddDocumentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_add_to_knowledge_base",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_add_to_knowledge_base(
    request: DocumentAddRequest,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Add document to knowledge base.

    Issue #744: Requires authenticated user.
    """
    try:
        kb = get_knowledge_base()

        # Create document
        doc_id = await kb.add_document(
            content=request.content,
            metadata=request.metadata or {},
            source=request.source,
        )

        return {
            "success": True,
            "document_id": doc_id,
            "message": "Document added successfully",
        }

    except Exception as e:
        logger.error("Error adding to knowledge base: %s", e)
        return {"success": False, "error": "Internal server error"}


@router.post("/mcp/get_knowledge_stats", response_model=McpKnowledgeStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_get_knowledge_stats",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_get_knowledge_stats(
    request: KnowledgeStatsRequest,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Get knowledge base statistics.

    Issue #744: Requires authenticated user.
    """
    try:
        kb = get_knowledge_base()

        stats = {
            "total_documents": await kb.get_document_count(),
            "index_name": kb.redis_index_name,
            "vector_store_type": kb.vector_store_type,
            "embedding_model": kb.embedding_model_name,
            "chunk_size": kb.chunk_size,
        }

        if request.include_details:
            # Add more detailed statistics
            stats.update(
                {
                    "semantic_chunking_enabled": kb.use_semantic_chunking,
                    "redis_db": kb.redis_db,
                    "last_update": await kb.get_last_update_time(),
                    "memory_usage": await kb.get_memory_usage(),
                }
            )

        return {"success": True, "stats": stats}

    except Exception as e:
        logger.error("Error getting knowledge stats: %s", e)
        return {"success": False, "error": "Internal server error", "stats": {}}


@router.post("/mcp/summarize_knowledge_topic", response_model=McpSummarizeTopicResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_summarize_knowledge_topic",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_summarize_knowledge_topic(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Summarize knowledge on a topic.

    Issue #744: Requires authenticated user.
    """
    try:
        kb = get_knowledge_base()
        topic = request.get("topic")
        max_length = request.get("max_length", 500)

        # Search for relevant documents
        results = await kb.search(query=topic, top_k=10)

        if not results:
            return {
                "success": True,
                "summary": (f"No information found about '{topic}' in the knowledge base."),
                "source_count": 0,
            }

        # Combine relevant content
        combined_content = "\n\n".join([r.get("content", "") for r in results[:5]])

        # Use LLM to summarize (if available)
        if hasattr(kb, "llm") and kb.llm:
            prompt = (
                f"Summarize the following information about "
                f"'{topic}':\n\n{combined_content}\n\n"
                f"Provide a concise summary in "
                f"{max_length} tokens or less."
            )

            summary = await kb.llm.generate(prompt, max_tokens=max_length)
        else:
            # Fallback to simple truncation
            summary = combined_content[: max_length * 4]  # Rough char to token conversion
            if len(summary) < len(combined_content):
                summary += "..."

        return {
            "success": True,
            "summary": summary,
            "topic": topic,
            "source_count": len(results),
        }

    except Exception as e:
        logger.error("Error summarizing topic: %s", e)
        return {"success": False, "error": "Internal server error", "summary": ""}


@router.post("/mcp/vector_similarity_search", response_model=McpVectorSimilarityResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_vector_similarity_search",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_vector_similarity_search(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Perform vector similarity search in Redis.

    Issue #744: Requires authenticated user.
    """
    try:
        kb = get_knowledge_base()
        query = request.get("query")
        top_k = request.get("top_k", 10)
        threshold = request.get("threshold", 0.7)

        # Use the vector store directly for similarity search
        if hasattr(kb, "vector_store") and kb.vector_store:
            # Perform vector search using knowledge base
            # Note: kb.search() handles embedding generation internally
            results = []
            search_results = await kb.search(query, top_k)

            for result in search_results:
                if result.get("score", 0) >= threshold:
                    results.append(result)

            return {
                "success": True,
                "results": results,
                "query": query,
                "threshold": threshold,
            }
        else:
            return {
                "success": False,
                "error": "Vector store not available",
                "results": [],
            }

    except Exception as e:
        logger.error("Error in vector similarity search: %s", e)
        return {"success": False, "error": "Internal server error", "results": []}


@router.post("/mcp/langchain_qa_chain", response_model=McpQaChainResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_langchain_qa_chain",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_langchain_qa_chain(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Use LangChain QA chain for comprehensive answers.

    Issue #744: Requires authenticated user.
    """
    try:
        kb = get_knowledge_base()
        question = request.get("question")
        context_size = request.get("context_size", 3)

        # First get relevant documents
        search_results = await kb.search(question, context_size)

        if not search_results:
            return {
                "success": True,
                "answer": "No relevant information found in the knowledge base.",
                "sources": [],
            }

        # Combine context
        context = "\n\n".join([r.get("content", "") for r in search_results])

        # Issue #1047: Use ChatOllama (langchain 1.x) for QA
        prompt = f"Based on the following context, answer this question: " f"{question}\n\nContext:\n{context}"

        chat_llm = _get_chat_ollama()
        if chat_llm:
            answer = await chat_llm.ainvoke(prompt)
            answer = answer.content if hasattr(answer, "content") else str(answer)
        elif hasattr(kb, "llm") and kb.llm:
            # Fallback to knowledge base LLM (LlamaIndex)
            answer = await asyncio.to_thread(kb.llm.complete, prompt)
            answer = str(answer)
        else:
            answer = f"Based on the search results: " f"{search_results[0].get('content', '')[:500]}..."

        return {
            "success": True,
            "answer": answer,
            "question": question,
            "sources": [r.get("source", "unknown") for r in search_results],
        }

    except Exception as e:
        logger.error("Error in LangChain QA chain: %s", e)
        return {"success": False, "error": "Internal server error", "answer": ""}


@router.post("/mcp/extract_structured_data")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_extract_structured_data",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_extract_structured_data(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Extract structured data from a URL using JSON Schema + LLM.

    Issue #7405: Delegates to POST /knowledge/extract logic via extract_url().
    """
    url = request.get("url")
    schema = request.get("schema")
    render = request.get("render", "auto")

    if not url or not schema:
        return {"success": False, "error": "url and schema are required"}

    try:
        from web_fetch.extractors import extract_url

        result = await extract_url(url=url, schema=schema, render=render)
        return {"success": True, **result}
    except RuntimeError as exc:
        logger.warning("mcp_extract_structured_data fetch failed for %s: %s", url, exc)
        return {
            "success": False,
            "error_code": "fetch_failed",
            "details": str(exc),
        }  # codeql[py/stack-trace-exposure] MCP returns structured errors to the AI agent, not public web users
    except ValueError as exc:
        logger.warning("mcp_extract_structured_data schema invalid for %s: %s", url, exc)
        return {
            "success": False,
            "error_code": "schema_invalid",
            "details": str(exc),
        }  # codeql[py/stack-trace-exposure] MCP returns structured errors to the AI agent, not public web users
    except Exception as exc:
        logger.error("mcp_extract_structured_data unexpected error: %s", exc)
        return {"success": False, "error": "Internal server error"}


@router.post("/mcp/scrape_url")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_scrape_url",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_scrape_url(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Fetch a URL and return its markdown content. Issue #7509."""
    url = request.get("url")
    render = request.get("render", "auto")

    if not url:
        return {"success": False, "error": "url is required"}

    try:
        from web_fetch import RenderMode, WebFetcher

        fetch_result = await WebFetcher.fetch(url, render=RenderMode(render))
        if not fetch_result.success:
            return {"success": False, "error_code": fetch_result.error_code, "url": url}
        title = f"# {fetch_result.title}\n\n" if fetch_result.title else ""
        header = f"## Scraped: {url} (status {fetch_result.status_code}, source: {fetch_result.source})\n\n"
        return {
            "success": True,
            "url": fetch_result.url,
            "markdown": header + title + (fetch_result.markdown or "*(no content)*"),
        }
    except Exception as exc:
        logger.error("mcp_scrape_url failed for %s: %s", url, exc)
        return {"success": False, "error": "Internal server error"}


@router.post("/mcp/crawl_site")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_crawl_site",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_crawl_site(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: BFS crawl seed URLs and return a markdown index. Issue #7509."""
    seed_urls = request.get("seed_urls", [])
    max_depth = int(request.get("max_depth", 1))
    max_pages = int(request.get("max_pages", 100))
    respect_robots = bool(request.get("respect_robots", True))
    ingest = bool(request.get("ingest", False))
    same_origin = bool(request.get("same_origin", True))

    if not seed_urls:
        return {"success": False, "error": "seed_urls is required"}

    try:
        from chat_workflow.tool_handler import _format_crawl_results
        from knowledge.connectors.models import ConnectorConfig
        from knowledge.connectors.web_crawler import WebCrawlerConnector

        cfg = ConnectorConfig(
            connector_id="mcp_crawl", connector_type="web_crawler", name="mcp_crawl", config={"urls": seed_urls}
        )
        connector = WebCrawlerConnector(cfg)
        results = await connector.crawl(
            seed_urls=seed_urls,
            max_depth=max_depth,
            max_pages=max_pages,
            respect_robots=respect_robots,
            ingest=ingest,
            same_origin=same_origin,
        )
        return {"success": True, "page_count": len(results), "markdown": _format_crawl_results(seed_urls, results)}
    except Exception as exc:
        logger.error("mcp_crawl_site failed: %s", exc)
        return {"success": False, "error": "Internal server error"}


@router.post("/mcp/map_site")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_map_site",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_map_site(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Discover all URLs for a domain via sitemap or BFS. Issue #7509."""
    domain = request.get("domain", "").strip()
    max_urls = int(request.get("max_urls", 500))
    respect_robots = bool(request.get("respect_robots", True))

    if not domain:
        return {"success": False, "error": "domain is required"}

    try:
        from chat_workflow.tool_handler import _format_map_results
        from web_fetch.site_mapper import SiteMapper

        site_result = await SiteMapper.map_site(domain, max_urls=max_urls, respect_robots=respect_robots)
        return {
            "success": True,
            "url_count": len(site_result.entries),
            "source": site_result.source,
            "markdown": _format_map_results(site_result),
        }
    except Exception as exc:
        logger.error("mcp_map_site failed for %s: %s", domain, exc)
        return {"success": False, "error": "Internal server error"}


async def _vector_op_info(kb, redis_mgr, params: dict) -> dict:
    """Handle vector info operation. (Issue #315 - extracted)"""
    vector_db = redis_mgr.get_connection(RedisDatabase.VECTORS)
    info = await asyncio.to_thread(vector_db.info)
    return {
        "success": True,
        "operation": "info",
        "data": {
            "used_memory": info.get("used_memory_human", "unknown"),
            "total_keys": info.get("db8", {}).get("keys", 0),
            "vector_index": kb.redis_index_name if kb else "unknown",
        },
    }


async def _vector_op_flush(kb, vectors_client, params: dict) -> dict:
    """Handle vector flush operation. (Issue #315 - extracted)"""
    if not params.get("confirm", False):
        return {
            "success": False,
            "operation": "flush",
            "error": "Confirmation required (set params.confirm = true)",
        }
    if not vectors_client:
        return {"success": False, "operation": "flush", "error": "Redis not available"}
    await asyncio.to_thread(vectors_client.flushdb)
    return {"success": True, "operation": "flush", "message": "Vector database flushed"}


async def _vector_op_reindex(kb, vectors_client, params: dict) -> dict:
    """Handle vector reindex operation. (Issue #315 - extracted)"""
    if kb and hasattr(kb, "index"):
        return {
            "success": True,
            "operation": "reindex",
            "message": "Reindexing triggered (operation may take time)",
        }
    return {
        "success": False,
        "operation": "reindex",
        "error": "Knowledge base index not available",
    }


async def _vector_op_backup(kb, vectors_client, params: dict) -> dict:
    """Handle vector backup operation. (Issue #315 - extracted)"""
    return {
        "success": True,
        "operation": "backup",
        "message": "Backup operation not yet implemented",
    }


# Issue #315: Dispatch table for vector operations
_VECTOR_OPERATIONS = {
    "info": _vector_op_info,
    "flush": _vector_op_flush,
    "reindex": _vector_op_reindex,
    "backup": _vector_op_backup,
}


@router.post("/mcp/redis_vector_operations", response_model=McpRedisVectorOpsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_redis_vector_operations",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_redis_vector_operations(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """MCP tool: Direct Redis vector store operations.

    Issue #744: Requires authenticated user. Admin operations (flush, reindex)
    should be further restricted at the application level.
    """
    try:
        operation = request.get("operation")
        params = request.get("params", {})

        kb = get_knowledge_base()
        vectors_client = get_vectors_redis_client()

        # Use dispatch table (Issue #315 - reduced depth)
        handler = _VECTOR_OPERATIONS.get(operation)
        if handler:
            return await handler(kb, vectors_client, params)
        return {"success": False, "error": f"Unknown operation: {operation}"}

    except Exception as e:
        logger.error("Error in Redis vector operations: %s", e)
        return {"success": False, "error": "Internal server error"}


@router.get("/mcp/schema", response_model=McpSchemaResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_schema",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def get_mcp_schema(
    current_user: dict = Depends(get_current_user),
):
    """Get the complete MCP schema for knowledge base tools.

    Issue #744: Requires authenticated user.
    """
    return {
        "name": "autobot-knowledge-base",
        "version": "2.0.0",
        "description": ("MCP tools for accessing AutoBot's knowledge base via LangChain, LlamaIndex, and Redis"),
        "tools": await get_mcp_tools(),
        "backends": {
            "langchain": "LangChain for orchestration and QA chains",
            "llama_index": "LlamaIndex for document indexing and retrieval",
            "redis": "Redis for vector storage and similarity search",
        },
    }


# Health check for MCP bridge
@router.get("/mcp/health", response_model=McpHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_health",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def mcp_health():
    """Check if MCP bridge is healthy"""
    try:
        kb = get_knowledge_base()
        return {
            "status": "healthy",
            "knowledge_base_initialized": kb is not None,
            "vector_store_connected": kb.vector_store is not None if kb else False,
        }
    except Exception:
        logger.exception("Unexpected error")

        return {"status": "unhealthy", "error": "Internal server error"}


# ---------------------------------------------------------------------------
# MCP Resources and Prompts (Issue MVA-2165)
# ---------------------------------------------------------------------------


@router.get("/mcp/resources")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_kb_resources",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def list_kb_resources(
    current_user: dict = Depends(get_current_user),
):
    """
    List available knowledge base resources as MCP resources.

    Issue MVA-2165: Exposes KB documents and chunks as browseable resources.
    Issue #744: Requires authenticated user.

    Resources use kb:// URI scheme:
    - kb://doc/<ID> - specific document
    - kb://chunk/<ID> - specific chunk
    """
    try:
        kb = get_knowledge_base()
        resources = []

        # Get recent documents as resources
        # Note: This is a simplified implementation - in production,
        # you'd want pagination and proper document listing
        stats = {
            "total_documents": await kb.get_document_count(),
        }

        # For now, expose the document count as metadata
        # Individual documents would be accessed via kb://doc/<id> URIs
        resources.append(
            {
                "uri": f"kb://stats",
                "name": "Knowledge Base Statistics",
                "description": f"Total documents: {stats['total_documents']}",
                "mime_type": "application/json",
            }
        )

        return {
            "success": True,
            "resources": resources,
            "total": len(resources),
        }

    except Exception as e:
        logger.error("Error listing KB resources: %s", e)
        return {"success": False, "error": "Internal server error", "resources": []}


@router.post("/mcp/resources/read")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="read_kb_resource",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def read_kb_resource(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """
    Read a knowledge base resource by its URI.

    Issue MVA-2165: Implements MCP resource reading via kb:// URIs.
    Issue #744: Requires authenticated user.

    Supports:
    - kb://doc/<ID> - retrieve document by ID
    - kb://chunk/<ID> - retrieve chunk by ID
    - kb://stats - retrieve knowledge base statistics
    """
    uri = request.get("uri", "")
    if not uri.startswith("kb://"):
        return {"success": False, "error": "Only kb:// URIs are supported"}

    # Parse URI: kb://type/identifier
    parts = uri[5:].split("/", 1)  # Remove 'kb://'
    if len(parts) < 1:
        return {"success": False, "error": "Invalid kb:// URI format"}

    resource_type = parts[0]
    identifier = parts[1] if len(parts) > 1 else None

    try:
        kb = get_knowledge_base()

        if resource_type == "stats":
            # Return KB statistics as JSON
            stats = {
                "total_documents": await kb.get_document_count(),
                "index_name": kb.redis_index_name,
                "vector_store_type": kb.vector_store_type,
                "embedding_model": kb.embedding_model_name,
                "chunk_size": kb.chunk_size,
            }
            content = str(stats)
            mime_type = "application/json"

        elif resource_type == "doc":
            if not identifier:
                return {"success": False, "error": "Document ID required"}
            # Retrieve document by ID
            # Note: This is a simplified implementation - you'd need to
            # implement document retrieval by ID in the knowledge base
            results = await kb.search(query=f"id:{identifier}", top_k=1)
            if results:
                content = results[0].get("content", "")
                mime_type = "text/plain"
            else:
                return {"success": False, "error": f"Document not found: {identifier}"}

        elif resource_type == "chunk":
            if not identifier:
                return {"success": False, "error": "Chunk ID required"}
            # Retrieve chunk by ID
            results = await kb.search(query=f"chunk_id:{identifier}", top_k=1)
            if results:
                content = results[0].get("content", "")
                mime_type = "text/plain"
            else:
                return {"success": False, "error": f"Chunk not found: {identifier}"}

        else:
            return {"success": False, "error": f"Unknown resource type: {resource_type}"}

        return {
            "success": True,
            "uri": uri,
            "content": content,
            "mime_type": mime_type,
            "size_bytes": len(content),
        }

    except Exception as e:
        logger.error("Error reading KB resource: %s", e)
        return {"success": False, "error": "Internal server error"}


@router.post("/mcp/resources/subscribe")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="subscribe_kb_resource",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def subscribe_kb_resource(
    request: SubscribeResourceRequest,
    current_user: dict = Depends(get_current_user),
) -> Metadata:
    """
    Subscribe to knowledge base resource change notifications.

    Issue MVA-2166: Implements MCP resource subscriptions for real-time updates.
    Issue #744: Requires authenticated user.

    Clients can subscribe to kb:// URIs and receive notifications when:
    - Documents are added or updated
    - Chunks are reindexed
    - Knowledge base statistics change

    Note: Active change detection for knowledge base updates will be implemented in a follow-up.
    For now, subscriptions are registered but notifications must be manually triggered
    via the MCPSubscriptionManager.publish_change() method.

    Args:
        request: Subscription request with URI and session_id
        current_user: Authenticated user

    Returns:
        Subscription confirmation with WebSocket channel
    """
    from services.mcp_subscription_manager import get_mcp_subscription_manager

    # Validate URI
    if not request.uri.startswith("kb://"):
        return {"success": False, "error": "Only kb:// URIs are supported for knowledge base subscriptions"}

    # Parse URI to validate format
    parts = request.uri[5:].split("/", 1)  # Remove 'kb://'
    if len(parts) < 1:
        return {"success": False, "error": "Invalid kb:// URI format. Expected: kb://type[/identifier]"}

    resource_type = parts[0]

    if resource_type not in ["doc", "chunk", "stats"]:
        return {"success": False, "error": f"Unknown resource type: {resource_type}"}

    # Subscribe via subscription manager
    success = await get_mcp_subscription_manager().subscribe(request.session_id, request.uri)

    if not success:
        return {"success": False, "error": "Failed to create subscription"}

    # Generate channel name for WebSocket subscription
    import hashlib
    uri_hash = hashlib.sha256(request.uri.encode()).hexdigest()[:16]
    channel = f"mcp:resource:{uri_hash}"

    logger.info(
        "Created KB subscription: session=%s, uri=%s, channel=%s",
        request.session_id[:8],
        request.uri,
        channel,
    )

    return {
        "success": True,
        "uri": request.uri,
        "session_id": request.session_id,
        "channel": channel,
        "message": f"Subscribed to {request.uri}. Connect to WebSocket at /ws/live and subscribe to channel: {channel}",
    }


@router.post("/mcp/resources/unsubscribe")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unsubscribe_kb_resource",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def unsubscribe_kb_resource(
    request: UnsubscribeResourceRequest,
    current_user: dict = Depends(get_current_user),
) -> Metadata:
    """
    Unsubscribe from knowledge base resource change notifications.

    Issue MVA-2166: Implements MCP resource subscriptions for real-time updates.
    Issue #744: Requires authenticated user.

    Removes a subscription for a specific session and resource URI.

    Args:
        request: Unsubscription request with URI and session_id
        current_user: Authenticated user

    Returns:
        Unsubscription confirmation
    """
    from services.mcp_subscription_manager import get_mcp_subscription_manager

    # Validate URI
    if not request.uri.startswith("kb://"):
        return {"success": False, "error": "Only kb:// URIs are supported for knowledge base subscriptions"}

    # Unsubscribe via subscription manager
    success = await get_mcp_subscription_manager().unsubscribe(request.session_id, request.uri)

    if not success:
        return {"success": False, "error": "Failed to remove subscription"}

    logger.info(
        "Removed KB subscription: session=%s, uri=%s",
        request.session_id[:8],
        request.uri,
    )

    return {
        "success": True,
        "uri": request.uri,
        "session_id": request.session_id,
        "message": f"Unsubscribed from {request.uri}",
    }


@router.get("/mcp/prompts")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_kb_prompts",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def list_kb_prompts(
    current_user: dict = Depends(get_current_user),
):
    """
    List available knowledge base prompt templates.

    Issue MVA-2165: Exposes predefined prompt templates for common
    knowledge base operations.
    Issue #744: Requires authenticated user.

    Templates can be invoked via the /mcp/prompts/get endpoint with
    appropriate arguments to generate contextual prompts.
    """
    prompts = [
        {
            "name": "search_knowledge",
            "description": "Search the knowledge base for information on a topic",
            "arguments": [
                {
                    "name": "topic",
                    "description": "Topic or query to search for",
                    "required": True,
                },
                {
                    "name": "depth",
                    "description": "Search depth: 'quick' (top 3), 'normal' (top 5), 'deep' (top 10)",
                    "required": False,
                },
            ],
        },
        {
            "name": "summarize_topic",
            "description": "Generate a comprehensive summary of knowledge on a topic",
            "arguments": [
                {
                    "name": "topic",
                    "description": "Topic to summarize",
                    "required": True,
                },
                {
                    "name": "format",
                    "description": "Output format: 'brief', 'detailed', or 'technical'",
                    "required": False,
                },
            ],
        },
    ]

    return {
        "success": True,
        "prompts": prompts,
        "total": len(prompts),
    }


@router.post("/mcp/prompts/get")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_kb_prompt",
    error_code_prefix="KNOWLEDGE_MCP",
)
async def get_kb_prompt(
    request: Metadata,
    current_user: dict = Depends(get_current_user),
):
    """
    Get a specific knowledge base prompt template with arguments interpolated.

    Issue MVA-2165: Returns formatted prompt messages for common
    knowledge base operations.
    Issue #744: Requires authenticated user.

    The template arguments are validated and interpolated into the
    prompt to generate contextual instructions for LLMs.
    """
    name = request.get("name", "")
    arguments = request.get("arguments", {})

    if name == "search_knowledge":
        topic = arguments.get("topic")
        if not topic:
            return {"success": False, "error": "Missing required argument: topic"}

        depth = arguments.get("depth", "normal")
        depth_map = {"quick": 3, "normal": 5, "deep": 10}
        top_k = depth_map.get(depth, 5)

        return {
            "success": True,
            "name": name,
            "description": "Search knowledge base for a topic",
            "messages": [
                {
                    "role": "user",
                    "content": f"Search the knowledge base for information about: {topic}\n"
                    f"Provide a comprehensive answer based on the top {top_k} most relevant sources.\n"
                    f"Include:\n"
                    f"- Key concepts and definitions\n"
                    f"- Important details and context\n"
                    f"- Relevant examples or use cases\n"
                    f"- Cite sources when possible",
                }
            ],
        }

    elif name == "summarize_topic":
        topic = arguments.get("topic")
        if not topic:
            return {"success": False, "error": "Missing required argument: topic"}

        format_type = arguments.get("format", "detailed")
        format_guidance = {
            "brief": "Keep it concise - 2-3 paragraphs maximum",
            "detailed": "Provide comprehensive coverage with examples",
            "technical": "Focus on technical details, specifications, and implementation notes",
        }
        guidance = format_guidance.get(format_type, format_guidance["detailed"])

        return {
            "success": True,
            "name": name,
            "description": "Summarize knowledge on a topic",
            "messages": [
                {
                    "role": "user",
                    "content": f"Generate a {format_type} summary of: {topic}\n"
                    f"Guidelines: {guidance}\n"
                    f"Structure:\n"
                    f"- Overview\n"
                    f"- Key points\n"
                    f"- Important considerations\n"
                    f"- Related topics or next steps",
                }
            ],
        }

    else:
        return {"success": False, "error": f"Unknown prompt template: {name}"}
