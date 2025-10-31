"""
AI Stack Integration API - Enhanced AI capabilities for AutoBot.

This module provides comprehensive API endpoints that integrate all AI Stack agents
from VM4 (172.16.168.24:8080) with the main AutoBot backend.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_config, get_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["ai-stack"], prefix="/api/ai-stack")

# ====================================================================
# Request/Response Models
# ====================================================================


class RAGQueryRequest(BaseModel):
    """RAG query request model."""

    query: str = Field(..., min_length=1, max_length=10000, description="Search query")
    documents: Optional[List[Dict[str, Any]]] = Field(
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
    chat_history: Optional[List[Dict[str, Any]]] = Field(
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
# Utility Functions
# ====================================================================


async def handle_ai_stack_error(
    error: AIStackError, context: str = "AI Stack operation"
):
    """Handle AI Stack errors with proper HTTP responses."""
    logger.error(f"{context} failed: {error.message}")

    status_code = 503  # Service Unavailable by default
    if error.status_code:
        if error.status_code >= 400 and error.status_code < 500:
            status_code = 400  # Bad Request for 4xx errors
        elif error.status_code >= 500:
            status_code = 503  # Service Unavailable for 5xx errors

    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error.message,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
            "ai_stack_details": error.details,
        },
    )


def create_success_response(
    data: Any, message: str = "Operation completed successfully"
) -> Dict[str, Any]:
    """Create standardized success response."""
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ====================================================================
# Health and Status Endpoints
# ====================================================================


@router.get("/health")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ai_stack_health_check",
    error_code_prefix="AI_STACK",
)
async def ai_stack_health_check():
    """Check AI Stack health and connectivity."""
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
        logger.error(f"AI Stack health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "AI Stack unavailable",
                "details": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get("/agents")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_ai_agents",
    error_code_prefix="AI_STACK",
)
async def list_ai_agents():
    """List all available AI agents."""
    ai_client = await get_ai_stack_client()
    agents = await ai_client.list_available_agents()

    return create_success_response(agents, "AI agents retrieved successfully")


# ====================================================================
# RAG (Retrieval-Augmented Generation) Endpoints
# ====================================================================


@router.post("/rag/query")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_query",
    error_code_prefix="AI_STACK",
)
async def rag_query(
    request: RAGQueryRequest, knowledge_base=Depends(get_knowledge_base)
):
    """
    Perform advanced RAG query with document synthesis.

    This endpoint combines the AutoBot knowledge base with AI Stack's
    RAG agent for enhanced retrieval and generation capabilities.
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
            logger.warning(f"Knowledge base search failed: {e}")
            documents = []

    # Perform RAG query with AI Stack
    rag_result = await ai_client.rag_query(
        query=request.query,
        documents=documents,
        context=request.context,
        max_results=request.max_results,
    )

    return create_success_response(rag_result, "RAG query completed successfully")


@router.post("/rag/reformulate")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reformulate_query",
    error_code_prefix="AI_STACK",
)
async def reformulate_query(query: str, context: Optional[str] = None):
    """Reformulate query for better retrieval results."""
    ai_client = await get_ai_stack_client()
    result = await ai_client.reformulate_query(query, context)

    return create_success_response(result, "Query reformulated successfully")


@router.post("/rag/analyze-documents")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_documents",
    error_code_prefix="AI_STACK",
)
async def analyze_documents(documents: List[Dict[str, Any]]):
    """Analyze and synthesize multiple documents."""
    ai_client = await get_ai_stack_client()
    result = await ai_client.analyze_documents(documents)

    return create_success_response(
        result, "Document analysis completed successfully"
    )


# ====================================================================
# Enhanced Chat Endpoints
# ====================================================================


@router.post("/chat/enhanced")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_chat",
    error_code_prefix="AI_STACK",
)
async def enhanced_chat(
    request: EnhancedChatRequest, knowledge_base=Depends(get_knowledge_base)
):
    """
    Enhanced chat with AI Stack integration and knowledge base support.

    This endpoint provides intelligent conversation with access to
    knowledge base and advanced AI reasoning capabilities.
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
                    [
                        f"- {item.get('content', '')[:200]}..."
                        for item in kb_context[:3]
                    ]
                )
                enhanced_context = (
                    f"{request.context or ''}\n\nRelevant knowledge:\n{kb_summary}"
                )
        except Exception as e:
            logger.warning(f"Knowledge base context enhancement failed: {e}")

    # Get response from AI Stack chat agent
    chat_result = await ai_client.chat_message(
        message=request.message,
        context=enhanced_context,
        chat_history=request.chat_history,
    )

    return create_success_response(
        chat_result, "Enhanced chat completed successfully"
    )


# ====================================================================
# Knowledge Enhancement Endpoints
# ====================================================================


@router.post("/knowledge/extract")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_knowledge",
    error_code_prefix="AI_STACK",
)
async def extract_knowledge(request: KnowledgeExtractionRequest):
    """Extract structured knowledge from content."""
    ai_client = await get_ai_stack_client()
    result = await ai_client.extract_knowledge(
        content=request.content,
        content_type=request.content_type,
        extraction_mode=request.extraction_mode,
    )

    return create_success_response(
        result, "Knowledge extraction completed successfully"
    )


@router.post("/knowledge/enhanced-search")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_knowledge_search",
    error_code_prefix="AI_STACK",
)
async def enhanced_knowledge_search(
    query: str,
    search_type: str = "comprehensive",
    max_results: int = 10,
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Enhanced knowledge search combining local KB and AI Stack capabilities.
    """
    ai_client = await get_ai_stack_client()

    # Parallel search: local KB + AI Stack enhanced search
    results = {}

    # Local knowledge base search
    if knowledge_base:
        try:
            local_results = await knowledge_base.search(
                query=query, top_k=max_results
            )
            results["local_kb"] = local_results
        except Exception as e:
            logger.warning(f"Local KB search failed: {e}")
            results["local_kb"] = []

    # AI Stack enhanced search
    try:
        enhanced_results = await ai_client.search_knowledge_enhanced(
            query=query, search_type=search_type, max_results=max_results
        )
        results["enhanced"] = enhanced_results
    except AIStackError as e:
        logger.warning(f"AI Stack enhanced search failed: {e}")
        results["enhanced"] = {}

    return create_success_response(results, "Enhanced knowledge search completed")


@router.get("/knowledge/system")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_knowledge",
    error_code_prefix="AI_STACK",
)
async def get_system_knowledge(knowledge_category: Optional[str] = None):
    """Get system-wide knowledge insights."""
    ai_client = await get_ai_stack_client()
    result = await ai_client.get_system_knowledge(knowledge_category)

    return create_success_response(
        result, "System knowledge retrieved successfully"
    )


# ====================================================================
# Research Endpoints
# ====================================================================


@router.post("/research/comprehensive")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="comprehensive_research",
    error_code_prefix="AI_STACK",
)
async def comprehensive_research(request: ResearchRequest):
    """Perform comprehensive research with multiple AI agents."""
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
            logger.warning(f"Web research failed: {e}")
            results["web_research"] = {"error": str(e)}

    return create_success_response(
        results, "Comprehensive research completed successfully"
    )


@router.post("/research/web")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="web_research",
    error_code_prefix="AI_STACK",
)
async def web_research(query: str, max_pages: int = 10, include_analysis: bool = True):
    """Perform web research with analysis."""
    ai_client = await get_ai_stack_client()
    result = await ai_client.web_research(
        query=query, max_pages=max_pages, include_analysis=include_analysis
    )

    return create_success_response(result, "Web research completed successfully")


# ====================================================================
# Development & Code Analysis Endpoints
# ====================================================================


@router.post("/development/search-code")
async def search_code(request: CodeSearchRequest):
    """Search codebase using NPU-accelerated AI."""
    try:
        ai_client = await get_ai_stack_client()
        result = await ai_client.search_code(
            query=request.query,
            search_scope=request.search_scope,
            include_npu=request.include_npu,
        )

        return create_success_response(result, "Code search completed successfully")
    except AIStackError as e:
        await handle_ai_stack_error(e, "Code search")


@router.post("/development/analyze-speedup")
async def analyze_development_speedup(request: DevelopmentAnalysisRequest):
    """Analyze codebase for development speedup opportunities."""
    try:
        ai_client = await get_ai_stack_client()
        result = await ai_client.analyze_development_speedup(
            code_path=request.code_path, analysis_type=request.analysis_type
        )

        return create_success_response(
            result, "Development speedup analysis completed successfully"
        )
    except AIStackError as e:
        await handle_ai_stack_error(e, "Development speedup analysis")


# ====================================================================
# Content Classification Endpoints
# ====================================================================


@router.post("/classification/classify")
async def classify_content(request: ContentClassificationRequest):
    """Classify content using AI classification agents."""
    try:
        ai_client = await get_ai_stack_client()
        result = await ai_client.classify_content(
            content=request.content, classification_types=request.classification_types
        )

        return create_success_response(
            result, "Content classification completed successfully"
        )
    except AIStackError as e:
        await handle_ai_stack_error(e, "Content classification")


# ====================================================================
# Multi-Agent Orchestration Endpoints
# ====================================================================


@router.post("/orchestrate/multi-agent-query")
async def multi_agent_query(
    query: str, agents: List[str], coordination_mode: str = "parallel"
):
    """
    Orchestrate multiple AI agents for complex query processing.

    Args:
        query: Query to process with multiple agents
        agents: List of agent names to use
        coordination_mode: How to coordinate agents (parallel, sequential)
    """
    try:
        ai_client = await get_ai_stack_client()
        results = {}

        if coordination_mode == "parallel":
            # Run agents in parallel
            agent_tasks = {}

            if "rag" in agents:
                try:
                    rag_result = await ai_client.rag_query(query=query, max_results=5)
                    results["rag"] = rag_result
                except Exception as e:
                    results["rag"] = {"error": str(e)}

            if "research" in agents:
                try:
                    research_result = await ai_client.research_query(query=query)
                    results["research"] = research_result
                except Exception as e:
                    results["research"] = {"error": str(e)}

            if "classification" in agents:
                try:
                    classification_result = await ai_client.classify_content(
                        content=query
                    )
                    results["classification"] = classification_result
                except Exception as e:
                    results["classification"] = {"error": str(e)}

            if "chat" in agents:
                try:
                    chat_result = await ai_client.chat_message(message=query)
                    results["chat"] = chat_result
                except Exception as e:
                    results["chat"] = {"error": str(e)}

        else:  # sequential mode
            # Run agents sequentially, each building on previous results
            context = query

            for agent in agents:
                try:
                    if agent == "rag":
                        result = await ai_client.rag_query(query=context, max_results=5)
                    elif agent == "research":
                        result = await ai_client.research_query(query=context)
                    elif agent == "classification":
                        result = await ai_client.classify_content(content=context)
                    elif agent == "chat":
                        result = await ai_client.chat_message(message=context)
                    else:
                        result = {"error": f"Unknown agent: {agent}"}

                    results[agent] = result

                    # Update context for next agent
                    if result.get("content"):
                        context = f"{context}\n\nPrevious result: {result['content']}"

                except Exception as e:
                    results[agent] = {"error": str(e)}

        return create_success_response(
            {
                "query": query,
                "coordination_mode": coordination_mode,
                "agents_used": agents,
                "results": results,
            },
            "Multi-agent query completed successfully",
        )

    except Exception as e:
        logger.error(f"Multi-agent query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ====================================================================
# Legacy Compatibility Endpoints
# ====================================================================


@router.post("/legacy/rag-search")
async def legacy_rag_search(query: str, max_results: int = 10):
    """Legacy RAG search endpoint for backward compatibility."""
    request = RAGQueryRequest(query=query, max_results=max_results)
    return await rag_query(request)


@router.post("/legacy/enhanced-chat")
async def legacy_enhanced_chat(message: str, context: Optional[str] = None):
    """Legacy enhanced chat endpoint for backward compatibility."""
    request = EnhancedChatRequest(message=message, context=context)
    return await enhanced_chat(request)
