# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AI Stack Integration API - Enhanced AI capabilities for AutoBot.

This module provides comprehensive API endpoints that integrate all AI Stack agents
from VM4 (uses NetworkConstants.AI_STACK_VM_IP) with the main AutoBot backend.
"""

from typing import Any, Awaitable, Callable, Dict, List

from fastapi import APIRouter, Depends

from api.schemas_agent import (
    ComprehensiveResearchData,
    KnowledgeSearchData,
    MultiAgentQueryData,
)
from api.schemas_ai_stack import (
    AIStackAgentsData,
    ChatResult,
    ClassificationResult,
    CodeSearchResult,
    DevelopmentSpeedupResult,
    DocumentAnalysisResult,
    KnowledgeExtractionResult,
    QueryReformulationResult,
    RAGQueryResult,
    SystemKnowledgeResult,
    WebResearchResult,
)
from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    ChatRequest,
    ContentClassificationRequest,
    DevelopmentAnalysisRequest,
    KbCodeSearchRequest,
    KnowledgeExtractionRequest,
    RAGQueryRequest,
    ResearchRequest,
)
from api.system_health import register_singleton_probe
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from dependencies import get_knowledge_base
from services.ai_stack_client import AIStackError, get_ai_stack_client
from type_defs.common import Metadata

# Import shared response utilities (Issue #292 - Eliminate duplicate code)
from utils.response_helpers import create_success_response

logger = get_logger(__name__)

# Type alias for agent handlers (Issue #336)
AgentQueryHandler = Callable[[Any, str], Awaitable[Dict[str, Any]]]

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["ai-stack"])

# ====================================================================
# Utility Functions (imported from backend.utils.response_helpers)
# ====================================================================
# handle_ai_stack_error and create_success_response are imported from
# backend.utils.response_helpers (Issue #292 - Eliminate duplicate code)


# ====================================================================
# Health and Status Endpoints
# ====================================================================


register_singleton_probe("ai_stack", get_ai_stack_client, async_getter=True)


@router.get("/agents", response_model=DataResponse[AIStackAgentsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_ai_agents",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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


@router.post("/rag/query", response_model=DataResponse[RAGQueryResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_query",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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
            kb_results = await knowledge_base.search(query=request.query, top_k=request.max_results)
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


@router.post("/rag/reformulate", response_model=DataResponse[QueryReformulationResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reformulate_query",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def reformulate_query(
    query: str,
    context: str | None = None,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Reformulate query for better retrieval results.

    Issue #744: Requires admin authentication.
    """
    ai_client = await get_ai_stack_client()
    result = await ai_client.reformulate_query(query, context)

    return create_success_response(result, "Query reformulated successfully")


@router.post("/rag/analyze-documents", response_model=DataResponse[DocumentAnalysisResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_documents",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def analyze_documents(documents: List[Metadata], admin_check: bool = Depends(check_admin_permission)):
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


@router.post("/chat/enhanced", response_model=DataResponse[ChatResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def enhanced_chat(
    request: ChatRequest,
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
                kb_summary = "\n".join([f"- {item.get('content', '')[:200]}..." for item in kb_context[:3]])
                enhanced_context = f"{request.context or ''}\n\nRelevant knowledge:\n{kb_summary}"
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


@router.post("/knowledge/extract", response_model=DataResponse[KnowledgeExtractionResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_knowledge",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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

    return create_success_response(result, "Knowledge extraction completed successfully")


@router.post("/knowledge/enhanced-search", response_model=DataResponse[KnowledgeSearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_knowledge_search",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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


@router.get("/knowledge/system", response_model=DataResponse[SystemKnowledgeResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_knowledge",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def get_system_knowledge(
    knowledge_category: str | None = None,
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


@router.post("/research/comprehensive", response_model=DataResponse[ComprehensiveResearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="comprehensive_research",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def comprehensive_research(request: ResearchRequest, admin_check: bool = Depends(check_admin_permission)):
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
            web_result = await ai_client.web_research(query=request.query, max_pages=10, include_analysis=True)
            results["web_research"] = web_result
        except AIStackError as e:
            logger.warning("Web research failed: %s", e)
            results["web_research"] = {"error": "Internal server error"}

    return create_success_response(results, "Comprehensive research completed successfully")


@router.post("/research/web", response_model=DataResponse[WebResearchResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="web_research",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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
    result = await ai_client.web_research(query=query, max_pages=max_pages, include_analysis=include_analysis)

    return create_success_response(result, "Web research completed successfully")


# ====================================================================
# Development & Code Analysis Endpoints
# ====================================================================


@router.post("/development/search-code", response_model=DataResponse[CodeSearchResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_code",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def search_code(request: KbCodeSearchRequest, admin_check: bool = Depends(check_admin_permission)):
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


@router.post("/development/analyze-speedup", response_model=DataResponse[DevelopmentSpeedupResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_development_speedup",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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

    return create_success_response(result, "Development speedup analysis completed successfully")


# ====================================================================
# Content Classification Endpoints
# ====================================================================


@router.post("/classification/classify", response_model=DataResponse[ClassificationResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="classify_content",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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

    return create_success_response(result, "Content classification completed successfully")


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


async def _execute_agent_query(ai_client: Any, agent: str, query: str) -> Dict[str, Any]:
    """Execute agent query with dispatch table (Issue #336 - extracted helper)."""
    handler = AGENT_QUERY_HANDLERS.get(agent)
    if handler:
        return await handler(ai_client, query)
    return {"error": f"Unknown agent: {agent}"}


async def _execute_parallel_agents(ai_client: Any, agents: List[str], query: str) -> Dict[str, Any]:
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
        except Exception:
            results[agent] = {"error": "Internal server error"}
    return results


async def _execute_sequential_agents(ai_client: Any, agents: List[str], query: str) -> Dict[str, Any]:
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
        except Exception:
            results[agent] = {"error": "Internal server error"}

    return results


# ====================================================================
# Multi-Agent Orchestration Endpoints
# ====================================================================


@router.post("/orchestrate/multi-agent-query", response_model=DataResponse[MultiAgentQueryData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="multi_agent_query",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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


@router.post("/legacy/rag-search", response_model=DataResponse[RAGQueryResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="legacy_rag_search",
    error_code_prefix="AI_STACK_INTEGRATION",
)
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


@router.post("/legacy/enhanced-chat", response_model=DataResponse[ChatResult])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="legacy_enhanced_chat",
    error_code_prefix="AI_STACK_INTEGRATION",
)
async def legacy_enhanced_chat(
    message: str,
    context: str | None = None,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Legacy enhanced chat endpoint for backward compatibility.

    Issue #744: Requires admin authentication.
    """
    request = ChatRequest(message=message, context=context)
    return await enhanced_chat(request)
