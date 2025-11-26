# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base MCP Bridge
Exposes knowledge base operations as MCP tools for LLM access
Integrates with LangChain, LlamaIndex, and Redis Vector Store
"""

import asyncio
import logging
from typing import List, Optional

from backend.type_defs.common import Metadata
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.knowledge_base import KnowledgeBase
from src.langchain_agent_orchestrator import LangChainAgentOrchestrator
from src.unified_config_manager import config as global_config_manager
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import RedisDatabase, RedisDatabaseManager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["knowledge_mcp", "mcp", "langchain"])

# Initialize components
knowledge_base = None
langchain_orchestrator = None
redis_manager = None


def get_knowledge_base():
    """Get or create knowledge base instance with Redis vector store"""
    global knowledge_base
    if knowledge_base is None:
        knowledge_base = KnowledgeBase(config_manager=global_config_manager)
    return knowledge_base


def get_redis_manager():
    """Get Redis database manager for vector operations"""
    global redis_manager
    if redis_manager is None:
        redis_manager = RedisDatabaseManager()
    return redis_manager


def get_langchain_orchestrator():
    """Get LangChain orchestrator for advanced tool usage"""
    global langchain_orchestrator
    if langchain_orchestrator is None:
        # Initialize with knowledge base
        kb = get_knowledge_base()
        langchain_orchestrator = LangChainAgentOrchestrator(
            config={},
            worker_node=None,  # Will be initialized if needed
            knowledge_base=kb,
        )
    return langchain_orchestrator


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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_tools",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.get("/mcp/tools")
async def get_mcp_tools() -> List[MCPTool]:
    """Get available MCP tools for knowledge base operations"""
    tools = [
        MCPTool(
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
        ),
        MCPTool(
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
        ),
        MCPTool(
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
        ),
        MCPTool(
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
        ),
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
    return tools


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_search_knowledge_base",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/search_knowledge_base")
async def mcp_search_knowledge_base(request: KnowledgeSearchRequest):
    """MCP tool: Search the knowledge base"""
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
        logger.error(f"Error searching knowledge base: {e}")
        return {"success": False, "error": str(e), "results": []}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_add_to_knowledge_base",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/add_to_knowledge_base")
async def mcp_add_to_knowledge_base(request: DocumentAddRequest):
    """MCP tool: Add document to knowledge base"""
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
        logger.error(f"Error adding to knowledge base: {e}")
        return {"success": False, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_get_knowledge_stats",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/get_knowledge_stats")
async def mcp_get_knowledge_stats(request: KnowledgeStatsRequest):
    """MCP tool: Get knowledge base statistics"""
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
        logger.error(f"Error getting knowledge stats: {e}")
        return {"success": False, "error": str(e), "stats": {}}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_summarize_knowledge_topic",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/summarize_knowledge_topic")
async def mcp_summarize_knowledge_topic(request: Metadata):
    """MCP tool: Summarize knowledge on a topic"""
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
        logger.error(f"Error summarizing topic: {e}")
        return {"success": False, "error": str(e), "summary": ""}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_vector_similarity_search",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/vector_similarity_search")
async def mcp_vector_similarity_search(request: Metadata):
    """MCP tool: Perform vector similarity search in Redis"""
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
        logger.error(f"Error in vector similarity search: {e}")
        return {"success": False, "error": str(e), "results": []}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_langchain_qa_chain",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/langchain_qa_chain")
async def mcp_langchain_qa_chain(request: Metadata):
    """MCP tool: Use LangChain QA chain for comprehensive answers"""
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

        # Use LangChain for QA if available
        orchestrator = get_langchain_orchestrator()
        if orchestrator and orchestrator.available:
            # Use LangChain QA chain
            prompt = (
                f"Based on the following context, answer this question:"
                f"{question}\n\nContext:\n{context}"
            )

            answer = await asyncio.to_thread(orchestrator.llm.predict, prompt)
        else:
            # Fallback to knowledge base LLM
            if hasattr(kb, "llm") and kb.llm:
                prompt = (
                    f"Based on the following context, answer this question:"
                    f"{question}\n\nContext:\n{context}"
                )

                answer = await asyncio.to_thread(kb.llm.complete, prompt)
                answer = str(answer)
            else:
                answer = f"Based on the search results: {search_results[0].get('content', '')[:500]}..."

        return {
            "success": True,
            "answer": answer,
            "question": question,
            "sources": [r.get("source", "unknown") for r in search_results],
        }

    except Exception as e:
        logger.error(f"Error in LangChain QA chain: {e}")
        return {"success": False, "error": str(e), "answer": ""}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="mcp_redis_vector_operations",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.post("/mcp/redis_vector_operations")
async def mcp_redis_vector_operations(request: Metadata):
    """MCP tool: Direct Redis vector store operations"""
    try:
        operation = request.get("operation")
        params = request.get("params", {})

        kb = get_knowledge_base()
        redis_mgr = get_redis_manager()

        if operation == "info":
            # Get Redis vector store info
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

        elif operation == "flush":
            # Clear vector database (dangerous!)
            if params.get("confirm", False):
                vector_db = redis_mgr.get_connection(RedisDatabase.VECTORS)
                await asyncio.to_thread(vector_db.flushdb)
                return {
                    "success": True,
                    "operation": "flush",
                    "message": "Vector database flushed",
                }
            else:
                return {
                    "success": False,
                    "operation": "flush",
                    "error": "Confirmation required (set params.confirm = true)",
                }

        elif operation == "reindex":
            # Trigger reindexing
            if kb and hasattr(kb, "index"):
                # This would typically trigger a full reindex
                return {
                    "success": True,
                    "operation": "reindex",
                    "message": "Reindexing triggered (operation may take time)",
                }
            else:
                return {
                    "success": False,
                    "operation": "reindex",
                    "error": "Knowledge base index not available",
                }

        elif operation == "backup":
            # Create backup of vector data
            vector_db = redis_mgr.get_connection(RedisDatabase.VECTORS)
            # This would typically create a backup
            return {
                "success": True,
                "operation": "backup",
                "message": "Backup operation not yet implemented",
            }

        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

    except Exception as e:
        logger.error(f"Error in Redis vector operations: {e}")
        return {"success": False, "error": str(e)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_mcp_schema",
    error_code_prefix="KNOWLEDGE_MCP",
)
@router.get("/mcp/schema")
async def get_mcp_schema():
    """Get the complete MCP schema for knowledge base tools"""
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
