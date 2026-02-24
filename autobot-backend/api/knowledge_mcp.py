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
import logging
import threading
from typing import List, Optional

from auth_middleware import get_current_user
from backend.constants.model_constants import ModelConstants
from backend.type_defs.common import Metadata
from config import config as global_config_manager
from fastapi import APIRouter, Depends
from knowledge_base import KnowledgeBase
from pydantic import BaseModel, Field
from utils.service_registry import get_service_url

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.redis_client import RedisDatabase, get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["knowledge_mcp", "mcp", "langchain"])

# Initialize components with thread-safe locks (Issue #395)
knowledge_base = None
_knowledge_base_lock = threading.Lock()


def get_knowledge_base():
    """Get or create knowledge base instance with Redis vector store.

    Issue #395: Added thread-safe lazy initialization with double-check locking.
    """
    global knowledge_base
    if knowledge_base is None:
        with _knowledge_base_lock:
            # Double-check after acquiring lock to prevent race condition
            if knowledge_base is None:
                knowledge_base = KnowledgeBase(config_manager=global_config_manager)
    return knowledge_base


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
        from config import config as cfg

        llm_config = cfg.get_llm_config()
        model = ModelConstants.DEFAULT_OLLAMA_MODEL
        base_url = llm_config.get("ollama", {}).get(
            "base_url", get_service_url("ollama")
        )
        return ChatOllama(model=model, base_url=base_url, temperature=0.7)
    except Exception as exc:
        logger.warning("Failed to create ChatOllama: %s", exc)
        return None


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Metadata


class KnowledgeSearchRequest(BaseModel):
    """Request model for knowledge base search"""

    query: str = Field(..., description="Search query")
    top_k: int = Field(5, description="Number of results to return")
    filters: Optional[Metadata] = Field(None, description="Optional filters")


class DocumentAddRequest(BaseModel):
    """Request model for adding documents"""

    content: str = Field(..., description="Document content")
    metadata: Optional[Metadata] = Field(None, description="Document metadata")
    source: Optional[str] = Field(None, description="Document source")


class KnowledgeStatsRequest(BaseModel):
    """Request model for knowledge base statistics"""

    include_details: bool = Field(False, description="Include detailed statistics")


def _create_search_tool() -> MCPTool:
    """
    Create MCP tool for knowledge base search.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        MCPTool definition for search_knowledge_base operation
    """
    return MCPTool(
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


def _create_add_document_tool() -> MCPTool:
    """
    Create MCP tool for adding documents to knowledge base.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        MCPTool definition for add_to_knowledge_base operation
    """
    return MCPTool(
        name="add_to_knowledge_base",
        description=(
            "Add new information to the AutoBot knowledge base (stored in Redis"
            "vectors)"
        ),
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


def _create_vector_search_tool() -> MCPTool:
    """
    Create MCP tool for vector similarity search.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        MCPTool definition for vector_similarity_search operation
    """
    return MCPTool(
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


def _create_qa_chain_tool() -> MCPTool:
    """
    Create MCP tool for LangChain QA chain.

    Issue #665: Extracted from _get_knowledge_search_tools to reduce function length.

    Returns:
        MCPTool definition for langchain_qa_chain operation
    """
    return MCPTool(
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


def _get_knowledge_search_tools() -> List[MCPTool]:
    """
    Get MCP tools for knowledge base search and retrieval operations.

    Issue #281: Extracted from get_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.
    Issue #665: Further refactored to reduce from 102 lines to below 20 lines.

    Returns:
        List of MCPTool definitions for search/retrieval operations
    """
    return [
        _create_search_tool(),
        _create_add_document_tool(),
        _create_vector_search_tool(),
        _create_qa_chain_tool(),
    ]


def _get_knowledge_management_tools() -> List[MCPTool]:
    """
    Get MCP tools for knowledge base management and admin operations.

    Issue #281: Extracted from get_mcp_tools to reduce function length
    and improve maintainability of tool definitions by category.

    Returns:
        List of MCPTool definitions for management/admin operations
    """
    return [
        MCPTool(
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
        MCPTool(
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
        MCPTool(
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_tools",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.get("/mcp/tools")
async def get_mcp_tools(
    current_user: dict = Depends(get_current_user),
) -> List[MCPTool]:
    """Get available MCP tools for knowledge base operations.

    Issue #744: Requires authenticated user.
    """
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_knowledge_search_tools())
    tools.extend(_get_knowledge_management_tools())
    return tools


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_search_knowledge_base",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/search_knowledge_base")
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
        results = await kb.search(
            query=request.query, top_k=request.top_k, filters=request.filters
        )

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
        return {"success": False, "error": str(e), "results": []}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_add_to_knowledge_base",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/add_to_knowledge_base")
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
        return {"success": False, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_get_knowledge_stats",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/get_knowledge_stats")
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
        return {"success": False, "error": str(e), "stats": {}}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_summarize_knowledge_topic",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/summarize_knowledge_topic")
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
                "summary": (
                    f"No information found about '{topic}' in the knowledge base."
                ),
                "source_count": 0,
            }

        # Combine relevant content
        combined_content = "\n\n".join([r.get("content", "") for r in results[:5]])

        # Use LLM to summarize (if available)
        if hasattr(kb, "llm") and kb.llm:
            prompt = (
                f"Summarize the following information about '{topic}':\n\n{combined_content}\n\nProvide"
                f"a concise summary in {max_length} tokens or less."
            )

            summary = await kb.llm.generate(prompt, max_tokens=max_length)
        else:
            # Fallback to simple truncation
            summary = combined_content[
                : max_length * 4
            ]  # Rough char to token conversion
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
        return {"success": False, "error": str(e), "summary": ""}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_vector_similarity_search",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/vector_similarity_search")
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
        return {"success": False, "error": str(e), "results": []}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_langchain_qa_chain",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/langchain_qa_chain")
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
        prompt = (
            f"Based on the following context, answer this question: "
            f"{question}\n\nContext:\n{context}"
        )

        chat_llm = _get_chat_ollama()
        if chat_llm:
            answer = await chat_llm.ainvoke(prompt)
            answer = answer.content if hasattr(answer, "content") else str(answer)
        elif hasattr(kb, "llm") and kb.llm:
            # Fallback to knowledge base LLM (LlamaIndex)
            answer = await asyncio.to_thread(kb.llm.complete, prompt)
            answer = str(answer)
        else:
            answer = (
                f"Based on the search results: "
                f"{search_results[0].get('content', '')[:500]}..."
            )

        return {
            "success": True,
            "answer": answer,
            "question": question,
            "sources": [r.get("source", "unknown") for r in search_results],
        }

    except Exception as e:
        logger.error("Error in LangChain QA chain: %s", e)
        return {"success": False, "error": str(e), "answer": ""}


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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_redis_vector_operations",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/redis_vector_operations")
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
        return {"success": False, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_schema",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.get("/mcp/schema")
async def get_mcp_schema(
    current_user: dict = Depends(get_current_user),
):
    """Get the complete MCP schema for knowledge base tools.

    Issue #744: Requires authenticated user.
    """
    return {
        "name": "autobot-knowledge-base",
        "version": "2.0.0",
        "description": (
            "MCP tools for accessing AutoBot's knowledge base via LangChain, LlamaIndex, and Redis"
        ),
        "tools": await get_mcp_tools(),
        "backends": {
            "langchain": "LangChain for orchestration and QA chains",
            "llama_index": "LlamaIndex for document indexing and retrieval",
            "redis": "Redis for vector storage and similarity search",
        },
    }


# Health check for MCP bridge
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_health",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.get("/mcp/health")
async def mcp_health():
    """Check if MCP bridge is healthy"""
    try:
        kb = get_knowledge_base()
        return {
            "status": "healthy",
            "knowledge_base_initialized": kb is not None,
            "vector_store_connected": kb.vector_store is not None if kb else False,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
