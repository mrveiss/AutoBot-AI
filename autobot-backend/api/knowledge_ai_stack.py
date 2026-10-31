# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Enhanced Knowledge Base API with AI Stack RAG Integration.

This module enhances the existing knowledge base with advanced AI capabilities
including RAG (Retrieval-Augmented Generation), knowledge extraction, and
intelligent content analysis using the AI Stack VM.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    AIStackDocumentAnalysisData,
    AIStackHealthStatusData,
    AIStackQueryReformulateData,
    AIStackRAGQueryRequest,
    AIStackRagSearchData,
    AIStackStatsData,
    AIStackSystemInsightsData,
    DocumentAnalysisRequest,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from dependencies import provide_knowledge_base
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.remote_read import admit_remote_read, remote_read_is_admin
from knowledge.search_filters import (
    extract_user_context_from_request,
    filter_search_results_by_permission,
)
from knowledge_factory import get_or_create_knowledge_base
from services.ai_stack_client import AIStackError, get_ai_stack_client
from utils.response_helpers import (
    create_error_response,
    create_success_response,
    handle_ai_stack_error,
)

logger = get_logger(__name__)

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["knowledge-aistack"])

# ====================================================================
# Request/Response Models
# ====================================================================


# ====================================================================
# Utility Functions - Now imported from backend.utils.response_helpers
# (Issue #292: Duplicate code elimination)
# ====================================================================


# ====================================================================
# #16908 (consolidated with #16716 in this PR): the enhanced-search endpoint
# that used to live here (Issue #281's _search_local_knowledge_base/
# _search_rag/_search_librarian/_combine_search_results/_run_all_search_sources
# helpers, and the POST /search handler itself) was deleted rather than
# re-pathed.
#
# It was registered at the same (method, path) as api/knowledge_search.py's
# POST /search, which always won (core router, registered earlier) -- so this
# handler was reachable by nothing. That was the SAFE outcome even after
# #16716 added tenant filtering to _search_local_knowledge_base() here: the
# surviving api/knowledge_search.py implementation already carries its own
# real tenant filtering (#15745). Re-pathing this dead handler to make it
# reachable would just duplicate that endpoint under a second path. If
# AI-Stack-combined search (local + RAG + librarian in one call) is still
# wanted as a feature, reviving it is a design decision, not a duplicate-route
# cleanup, and isn't reconstructed here.
# ====================================================================


@router.post("/search/rag", response_model=DataResponse[AIStackRagSearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_search",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def rag_search(
    request_data: AIStackRAGQueryRequest,
    knowledge_base=Depends(provide_knowledge_base),
    current_user: dict = Depends(get_current_user),
):
    """
    Pure RAG search using AI Stack for document synthesis and generation.

    This endpoint uses the AI Stack's RAG agent for advanced document
    understanding and context-aware response generation.

    Issue #744: Requires authenticated user.
    Issue #16665: locally-retrieved documents are scoped to the caller before
    being used as RAG context. Issue #16654/#16745: no admin bypass here.
    """
    try:
        ai_client = await get_ai_stack_client()

        # If no specific documents provided, search local knowledge base first
        documents = request_data.documents
        if not documents and knowledge_base:
            try:
                # Issue #13009: exclude quarantined research facts (#12622).
                kb_results = await knowledge_base.search(
                    query=request_data.query,
                    top_k=15,  # Get more documents for RAG context
                    filters=RESEARCH_QUARANTINE_FILTER,
                )
                kb_results = kb_results if isinstance(kb_results, list) else []
                user_id, user_org_id, user_group_ids = extract_user_context_from_request(current_user)
                documents = await filter_search_results_by_permission(
                    kb_results,
                    user_id,
                    user_org_id,
                    user_group_ids,
                    ownership_manager=getattr(knowledge_base, "ownership_manager", None),
                )
                logger.info(f"Retrieved {len(documents)} documents from local KB for RAG")
            except Exception as e:
                logger.warning("Local KB document retrieval failed: %s", e)
                documents = []

        # Perform RAG query
        rag_result = await ai_client.rag_query(
            query=request_data.query,
            documents=documents,
            context=request_data.context,
            max_results=request_data.max_results,
        )

        return create_success_response(
            {
                "query": request_data.query,
                "rag_response": rag_result,
                "documents_used": len(documents) if documents else 0,
                "include_reasoning": request_data.include_reasoning,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "RAG search")


@router.post("/analyze/documents", response_model=DataResponse[AIStackDocumentAnalysisData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_documents",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def analyze_documents(
    request_data: DocumentAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze multiple documents using AI Stack capabilities.

    This endpoint provides comprehensive document analysis including
    entity extraction, summarization, and cross-document insights.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Analyze documents using AI Stack
        analysis_result = await ai_client.analyze_documents(documents=request_data.documents)

        return create_success_response(
            {
                "documents_analyzed": len(request_data.documents),
                "analysis_type": request_data.analysis_type,
                "analysis_result": analysis_result,
                "extract_entities": request_data.extract_entities,
                "generate_summary": request_data.generate_summary,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Document analysis")


# ====================================================================
# Query Enhancement Endpoints
# ====================================================================


@router.post("/query/reformulate", response_model=DataResponse[AIStackQueryReformulateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reformulate_query",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def reformulate_query(
    query: str,
    context: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Reformulate query for better search results using AI Stack.

    This endpoint uses AI Stack's RAG agent to suggest improved
    query formulations for better retrieval performance.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        reformulation_result = await ai_client.reformulate_query(query=query, context=context)

        return create_success_response(
            {
                "original_query": query,
                "reformulated_queries": reformulation_result,
                "context_provided": context is not None,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Query reformulation")


# ====================================================================
# System Knowledge Management
# ====================================================================


@router.get("/system/insights", response_model=DataResponse[AIStackSystemInsightsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_knowledge_insights",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def get_system_knowledge_insights(
    knowledge_category: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Get system-wide knowledge insights and analytics.

    This endpoint provides insights about the knowledge base
    using AI Stack's system knowledge manager.

    Issue #744: Requires authenticated user.
    #16665: the remote service gets no caller identity and its store is not visible from this repo, so only an
    admin reads it, audited (``knowledge.remote_read``); anyone else is refused.
    """
    await admit_remote_read(current_user, "system_insights")
    try:
        ai_client = await get_ai_stack_client()

        insights = await ai_client.get_system_knowledge(knowledge_category=knowledge_category)

        return create_success_response({"knowledge_category": knowledge_category, "system_insights": insights})

    except AIStackError as e:
        await handle_ai_stack_error(e, "System knowledge insights")


# ====================================================================
# Enhanced Statistics and Health
# ====================================================================


async def _local_kb_stats(req: Request, current_user: dict) -> dict:
    """The local KB statistics: admin only, as the equivalent ``/stats`` is (#16665); withheld otherwise."""
    if not remote_read_is_admin(current_user):
        return {"withheld": "admin permission required"}
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
        return await kb_to_use.get_stats() if kb_to_use else {}
    except Exception as e:
        logger.warning("Failed to get local KB stats: %s", e)
        return {"error": "Internal server error"}


async def _ai_stack_insights(current_user: dict) -> dict:
    """The AI Stack's system knowledge for the stats payload: admin only, audited; withheld otherwise (#16665)."""
    if not remote_read_is_admin(current_user):
        return {"withheld": "admin permission required"}
    await admit_remote_read(current_user, "ai_stack_stats")
    try:
        return await (await get_ai_stack_client()).get_system_knowledge()
    except Exception as e:
        logger.warning("Failed to get AI Stack stats: %s", e)
        return {"error": "Internal server error"}


@router.get("/ai-stack/stats", response_model=DataResponse[AIStackStatsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_aistack_stats",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def get_aistack_stats(
    req: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Get enhanced knowledge base statistics including AI Stack metrics.

    #16908: path corrected from "/stats" to "/ai-stack/stats" -- it collided
    with (and always lost to) api/knowledge.py's own /stats, registered as a
    core router before this one. "/ai-stack/stats" matches the path this
    handler's own generated OpenAPI type already documented.

    Issue #744: Requires authenticated user.
    """
    try:
        local_stats = await _local_kb_stats(req, current_user)
        ai_stats = await _ai_stack_insights(current_user)

        return create_success_response(
            {
                "local_knowledge_base": local_stats,
                "ai_stack_insights": ai_stats,
                "enhanced_capabilities": True,
                "timestamp": utc_timestamp(),
            }
        )

    except HTTPException:
        raise  # an unwritable audit entry (503) is the answer, not a 500 envelope
    except Exception as e:
        logger.error("Enhanced stats retrieval failed: %s", e)
        return create_error_response(
            error_code="STATS_ERROR",
            message="Failed to retrieve enhanced stats",
            status_code=500,
        )


@router.get("/health/status", response_model=DataResponse[AIStackHealthStatusData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="knowledge_health",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def knowledge_health(
    current_user: dict = Depends(get_current_user),
):
    """
    Health check including AI Stack connectivity.

    Issue #744: Requires authenticated user.
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": utc_timestamp(),
            "components": {},
        }

        # Check AI Stack connectivity
        try:
            ai_client = await get_ai_stack_client()
            ai_health = await ai_client.health_check()
            health_status["components"]["ai_stack"] = ai_health["status"]
        except Exception:
            health_status["components"]["ai_stack"] = "unavailable"
            health_status["ai_stack_error"] = "unavailable"

        # Overall health assessment
        overall_healthy = health_status["components"]["ai_stack"] == "healthy"
        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(status_code=200 if overall_healthy else 503, content=health_status)

    except Exception as e:
        logger.error("AI Stack knowledge health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": "Internal server error",
                "timestamp": utc_timestamp(),
            },
        )
