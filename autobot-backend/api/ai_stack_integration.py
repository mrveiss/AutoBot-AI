# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI Stack Integration API - Enhanced AI capabilities for AutoBot.

This module provides comprehensive API endpoints that integrate all AI Stack agents
from VM4 (uses NetworkConstants.AI_STACK_VM_IP) with the main AutoBot backend.
"""

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.dependencies import get_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from backend.type_defs.common import Metadata

# Import shared response utilities (Issue #292 - Eliminate duplicate code)
from backend.utils.response_helpers import create_success_response

logger = logging.getLogger(__name__)

# Type alias for agent handlers (Issue #336)
AgentQueryHandler = Callable[[Any, str], Awaitable[Dict[str, Any]]]

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["ai-stack"])

# ====================================================================
# Request/Response Models
# ====================================================================


class RAGQueryRequest(BaseModel):
    """RAG query request model."""

    query: str = Field(..., min_length=1, max_length=10000, description="Search query")
    documents: Optional[List[Metadata]] = Field(
        None, description="Pre-retrieved documents"
    )
    context: Optional[str] = Field(None, description="Additional context")
    max_results: int = Field(10, ge=1, le=50, description="Maximum results to return")


class EnhancedChatRequest(BaseModel):
    """Enhanced chat request model."""

    message: str = Field(
        ..., min_length=1, max_length=50000, description="Chat message"
    )
    context: Optional[str] = Field(None, description="Conversation context")
    chat_history: Optional[List[Metadata]] = Field(
        None, description="Previous messages"
    )
    use_knowledge_base: bool = Field(True, description="Whether to use knowledge base")
    response_style: str = Field("conversational", description="Response style")


class KnowledgeExtractionRequest(BaseModel):
    """Knowledge extraction request model."""

    content: str = Field(
        ..., min_length=1, description="Content to extract knowledge from"
    )
    content_type: str = Field("text", description="Content type (text, document, url)")
    extraction_mode: str = Field("comprehensive", description="Extraction detail level")


class ResearchRequest(BaseModel):
    """Research request model."""

    query: str = Field(..., min_length=1, max_length=5000, description="Research query")
    research_depth: str = Field("comprehensive", description="Research depth")
    sources: Optional[List[str]] = Field(None, description="Specific sources")
    include_web: bool = Field(True, description="Include web research")


class CodeSearchRequest(BaseModel):
    """Code search request model."""

    query: str = Field(..., min_length=1, description="Code search query")
    search_scope: str = Field("codebase", description="Search scope")
    include_npu: bool = Field(True, description="Use NPU acceleration")


class DevelopmentAnalysisRequest(BaseModel):
    """Development analysis request model."""

    code_path: Optional[str] = Field(None, description="Specific path to analyze")
    analysis_type: str = Field("comprehensive", description="Analysis type")


class ContentClassificationRequest(BaseModel):
    """Content classification request model."""

    content: str = Field(..., min_length=1, description="Content to classify")
    classification_types: Optional[List[str]] = Field(
        None, description="Classification types"
    )


# ====================================================================
# Utility Functions (imported from backend.utils.response_helpers)
# ====================================================================
# handle_ai_stack_error and create_success_response are imported from
# backend.utils.response_helpers (Issue #292 - Eliminate duplicate code)


# ====================================================================
# Health and Status Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ai_stack_health_check",
    error_code_prefix="AI_STACK",
)
@router.get("/health")
async def ai_stack_health_check(admin_check: bool = Depends(check_admin_permission)):
    """
    Check AI Stack health and connectivity.

    Issue #744: Requires admin authentication.
    """
    try:
        ai_client = await get_ai_stack_client()
        health_status = await ai_client.health_check()

        return JSONResponse(
            status_code=200 if health_status["status"] == "healthy" else 503,
            content=create_success_response(
                health_status, "AI Stack health check completed"
            ),
        )
    except Exception as e:
        logger.error("AI Stack health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "AI Stack unavailable",
                "details": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_ai_agents",
    error_code_prefix="AI_STACK",
)
@router.get("/agents")
async def list_ai_agents(admin_check: bool = Depends(check_admin_permission)):
    """
    List all available AI agents.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    agents = await ai_client.list_available_agents()

    return create_success_response(agents, "AI agents retrieved successfully")


# ====================================================================
# RAG (Retrieval-Augmented Generation) Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_query",
    error_code_prefix="AI_STACK",
)
@router.post("/rag/query")
async def rag_query(
    request: RAGQueryRequest,
    admin_check: bool = Depends(check_admin_permission),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Perform advanced RAG query with document synthesis.

    This endpoint combines the AutoBot knowledge base with AI Stack's
    RAG agent for enhanced retrieval and generation capabilities.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()

    # First, search local knowledge base if no documents provided
    documents = request.documents
    if not documents and knowledge_base:
        try:
            kb_results = await knowledge_base.search(
                query=request.query, top_k=request.max_results
            )
            documents = kb_results if isinstance(kb_results, list) else []
        except Exception as e:
            logger.warning("Knowledge base search failed: %s", e)
            documents = []

    # Perform RAG query with AI Stack
    rag_result = await ai_client.rag_query(
        query=request.query,
        documents=documents,
        context=request.context,
        max_results=request.max_results,
    )

    return create_success_response(rag_result, "RAG query completed successfully")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reformulate_query",
    error_code_prefix="AI_STACK",
)
@router.post("/rag/reformulate")
async def reformulate_query(
    query: str,
    context: Optional[str] = None,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Reformulate query for better retrieval results.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.reformulate_query(query, context)

    return create_success_response(result, "Query reformulated successfully")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_documents",
    error_code_prefix="AI_STACK",
)
@router.post("/rag/analyze-documents")
async def analyze_documents(
    documents: List[Metadata], admin_check: bool = Depends(check_admin_permission)
):
    """
    Analyze and synthesize multiple documents.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.analyze_documents(documents)

    return create_success_response(result, "Document analysis completed successfully")


# ====================================================================
# Enhanced Chat Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat",
    error_code_prefix="AI_STACK",
)
@router.post("/chat/enhanced")
async def enhanced_chat(
    request: EnhancedChatRequest,
    admin_check: bool = Depends(check_admin_permission),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Enhanced chat with AI Stack integration and knowledge base support.

    This endpoint provides intelligent conversation with access to
    knowledge base and advanced AI reasoning capabilities.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()

    # Enhance context with knowledge base if requested
    enhanced_context = request.context
    if request.use_knowledge_base and knowledge_base:
        try:
            # Search knowledge base for relevant context
            kb_context = await knowledge_base.search(query=request.message, top_k=5)
            if kb_context:
                kb_summary = "\n".join(
                    [f"- {item.get('content', '')[:200]}..." for item in kb_context[:3]]
                )
                enhanced_context = (
                    f"{request.context or ''}\n\nRelevant knowledge:\n{kb_summary}"
                )
        except Exception as e:
            logger.warning("Knowledge base context enhancement failed: %s", e)

    # Get response from AI Stack chat agent
    chat_result = await ai_client.chat_message(
        message=request.message,
        context=enhanced_context,
        chat_history=request.chat_history,
    )

    return create_success_response(chat_result, "Enhanced chat completed successfully")


# ====================================================================
# Knowledge Enhancement Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_knowledge",
    error_code_prefix="AI_STACK",
)
@router.post("/knowledge/extract")
async def extract_knowledge(
    request: KnowledgeExtractionRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Extract structured knowledge from content.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.extract_knowledge(
        content=request.content,
        content_type=request.content_type,
        extraction_mode=request.extraction_mode,
    )

    return create_success_response(
        result, "Knowledge extraction completed successfully"
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_knowledge_search",
    error_code_prefix="AI_STACK",
)
@router.post("/knowledge/enhanced-search")
async def enhanced_knowledge_search(
    query: str,
    search_type: str = "comprehensive",
    max_results: int = 10,
    admin_check: bool = Depends(check_admin_permission),
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Enhanced knowledge search combining local KB and AI Stack capabilities.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()

    # Parallel search: local KB + AI Stack enhanced search
    results = {}

    # Local knowledge base search
    if knowledge_base:
        try:
            local_results = await knowledge_base.search(query=query, top_k=max_results)
            results["local_kb"] = local_results
        except Exception as e:
            logger.warning("Local KB search failed: %s", e)
            results["local_kb"] = []

    # AI Stack enhanced search
    try:
        enhanced_results = await ai_client.search_knowledge_enhanced(
            query=query, search_type=search_type, max_results=max_results
        )
        results["enhanced"] = enhanced_results
    except AIStackError as e:
        logger.warning("AI Stack enhanced search failed: %s", e)
        results["enhanced"] = {}

    return create_success_response(results, "Enhanced knowledge search completed")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_knowledge",
    error_code_prefix="AI_STACK",
)
@router.get("/knowledge/system")
async def get_system_knowledge(
    knowledge_category: Optional[str] = None,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get system-wide knowledge insights.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.get_system_knowledge(knowledge_category)

    return create_success_response(result, "System knowledge retrieved successfully")


# ====================================================================
# Research Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="comprehensive_research",
    error_code_prefix="AI_STACK",
)
@router.post("/research/comprehensive")
async def comprehensive_research(
    request: ResearchRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Perform comprehensive research with multiple AI agents.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    results = {}

    # Core research
    research_result = await ai_client.research_query(
        query=request.query,
        research_depth=request.research_depth,
        sources=request.sources,
    )
    results["research"] = research_result

    # Web research if requested
    if request.include_web:
        try:
            web_result = await ai_client.web_research(
                query=request.query, max_pages=10, include_analysis=True
            )
            results["web_research"] = web_result
        except AIStackError as e:
            logger.warning("Web research failed: %s", e)
            results["web_research"] = {"error": str(e)}

    return create_success_response(
        results, "Comprehensive research completed successfully"
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="web_research",
    error_code_prefix="AI_STACK",
)
@router.post("/research/web")
async def web_research(
    query: str,
    max_pages: int = 10,
    include_analysis: bool = True,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Perform web research with analysis.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.web_research(
        query=query, max_pages=max_pages, include_analysis=include_analysis
    )

    return create_success_response(result, "Web research completed successfully")


# ====================================================================
# Development & Code Analysis Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_code",
    error_code_prefix="AI_STACK",
)
@router.post("/development/search-code")
async def search_code(
    request: CodeSearchRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Search codebase using NPU-accelerated AI.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.search_code(
        query=request.query,
        search_scope=request.search_scope,
        include_npu=request.include_npu,
    )

    return create_success_response(result, "Code search completed successfully")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_development_speedup",
    error_code_prefix="AI_STACK",
)
@router.post("/development/analyze-speedup")
async def analyze_development_speedup(
    request: DevelopmentAnalysisRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Analyze codebase for development speedup opportunities.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.analyze_development_speedup(
        code_path=request.code_path, analysis_type=request.analysis_type
    )

    return create_success_response(
        result, "Development speedup analysis completed successfully"
    )


# ====================================================================
# Content Classification Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="classify_content",
    error_code_prefix="AI_STACK",
)
@router.post("/classification/classify")
async def classify_content(
    request: ContentClassificationRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Classify content using AI classification agents.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.classify_content(
        content=request.content, classification_types=request.classification_types
    )

    return create_success_response(
        result, "Content classification completed successfully"
    )


# ====================================================================
# Multi-Agent Orchestration Helpers (Issue #336)
# ====================================================================


async def _query_rag_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query RAG agent (Issue #336 - extracted handler)."""
    return await ai_client.rag_query(query=query, max_results=5)


async def _query_research_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query research agent (Issue #336 - extracted handler)."""
    return await ai_client.research_query(query=query)


async def _query_classification_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query classification agent (Issue #336 - extracted handler)."""
    return await ai_client.classify_content(content=query)


async def _query_chat_agent(ai_client: Any, query: str) -> Dict[str, Any]:
    """Query chat agent (Issue #336 - extracted handler)."""
    return await ai_client.chat_message(message=query)


# Issue #336: Dispatch table for agent query handlers
AGENT_QUERY_HANDLERS: Dict[str, AgentQueryHandler] = {
    "rag": _query_rag_agent,
    "research": _query_research_agent,
    "classification": _query_classification_agent,
    "chat": _query_chat_agent,
}


async def _execute_agent_query(
    ai_client: Any, agent: str, query: str
) -> Dict[str, Any]:
    """Execute agent query with dispatch table (Issue #336 - extracted helper)."""
    handler = AGENT_QUERY_HANDLERS.get(agent)
    if handler:
        return await handler(ai_client, query)
    return {"error": f"Unknown agent: {agent}"}


async def _execute_parallel_agents(
    ai_client: Any, agents: List[str], query: str
) -> Dict[str, Any]:
    """Execute agents in parallel mode (Issue #315: extracted to reduce nesting).

    Args:
        ai_client: AI Stack client instance
        agents: List of agent names to query
        query: Query string

    Returns:
        Dict mapping agent names to their results
    """
    results: Dict[str, Any] = {}
    for agent in agents:
        if agent not in AGENT_QUERY_HANDLERS:
            continue
        try:
            results[agent] = await _execute_agent_query(ai_client, agent, query)
        except Exception as e:
            results[agent] = {"error": str(e)}
    return results


async def _execute_sequential_agents(
    ai_client: Any, agents: List[str], query: str
) -> Dict[str, Any]:
    """Execute agents sequentially, each building on previous (Issue #315: extracted).

    Args:
        ai_client: AI Stack client instance
        agents: List of agent names to query
        query: Initial query string

    Returns:
        Dict mapping agent names to their results
    """
    results: Dict[str, Any] = {}
    context = query

    for agent in agents:
        try:
            result = await _execute_agent_query(ai_client, agent, context)
            results[agent] = result
            # Update context for next agent
            if result.get("content"):
                context = f"{context}\n\nPrevious result: {result['content']}"
        except Exception as e:
            results[agent] = {"error": str(e)}

    return results


# ====================================================================
# Multi-Agent Orchestration Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="multi_agent_query",
    error_code_prefix="AI_STACK",
)
@router.post("/orchestrate/multi-agent-query")
async def multi_agent_query(
    query: str,
    agents: List[str],
    coordination_mode: str = "parallel",
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Orchestrate multiple AI agents for complex query processing.

    Args:
        query: Query to process with multiple agents
        agents: List of agent names to use
        coordination_mode: How to coordinate agents (parallel, sequential)

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()

    # Issue #315: Use extracted helpers to reduce nesting
    if coordination_mode == "parallel":
        results = await _execute_parallel_agents(ai_client, agents, query)
    else:
        results = await _execute_sequential_agents(ai_client, agents, query)

    return create_success_response(
        {
            "query": query,
            "coordination_mode": coordination_mode,
            "agents_used": agents,
            "results": results,
        },
        "Multi-agent query completed successfully",
    )


# ====================================================================
# Legacy Compatibility Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="legacy_rag_search",
    error_code_prefix="AI_STACK",
)
@router.post("/legacy/rag-search")
async def legacy_rag_search(
    query: str,
    max_results: int = 10,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Legacy RAG search endpoint for backward compatibility.

    Issue #744: Requires admin authentication.
    """
    request = RAGQueryRequest(query=query, max_results=max_results)
    return await rag_query(request)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="legacy_enhanced_chat",
    error_code_prefix="AI_STACK",
)
@router.post("/legacy/enhanced-chat")
async def legacy_enhanced_chat(
    message: str,
    context: Optional[str] = None,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Legacy enhanced chat endpoint for backward compatibility.

    Issue #744: Requires admin authentication.
    """
    request = EnhancedChatRequest(message=message, context=context)
    return await enhanced_chat(request)
