# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Search API - Search and RAG-enhanced query endpoints.

This module contains all search-related API endpoints for the knowledge base.
Extracted from knowledge.py for better maintainability (Issue #185, #209).

Endpoints:
- POST /search - Basic knowledge search with optional RAG
- POST /enhanced_search - Enhanced search with tags, hybrid mode, reranking
- POST /rag_search - Full RAG-enhanced search with query reformulation
- POST /similarity_search - Similarity search with threshold filtering

Related Issues: #78 (Search Quality), #185 (Split), #209 (Knowledge split)
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request

from backend.api.knowledge_models import EnhancedSearchRequest
from backend.knowledge_factory import get_or_create_knowledge_base
from backend.type_defs.common import Metadata
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import RAG Agent for enhanced search capabilities
try:
    from src.agents.rag_agent import get_rag_agent

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# Import Advanced RAG Service for reranking
try:
    from backend.services.rag_service import RAGService

    ADVANCED_RAG_AVAILABLE = True
except ImportError:
    ADVANCED_RAG_AVAILABLE = False
    logging.warning("Advanced RAG Service not available - reranking features disabled")

logger = logging.getLogger(__name__)

# Create router for search endpoints
router = APIRouter(tags=["knowledge-search"])

# Performance optimization: O(1) lookup for valid search modes (Issue #326)
VALID_SEARCH_MODES = {"vector", "text", "auto"}


# ===== SEARCH ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_knowledge",
    error_code_prefix="KB",
)
@router.post("/search")
async def search_knowledge(request: dict, req: Request):
    """
    Search knowledge base with optional RAG enhancement.
    FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "results": [],
            "total_results": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    limit = request.get("limit", 10)  # Also accept 'limit' for compatibility
    mode = request.get("mode", "auto")
    use_rag = request.get("use_rag", False)  # Old RAG enhancement parameter
    enable_reranking = request.get("enable_reranking", False)  # NEW: Advanced reranking

    # Use limit if provided, otherwise use top_k
    search_limit = limit if request.get("limit") is not None else top_k

    logger.info(
        f"Knowledge search request: '{query}' (top_k={search_limit}, mode={mode}, "
        f"use_rag={use_rag}, enable_reranking={enable_reranking})"
    )

    # Check if knowledge base is empty - fast check to avoid timeout
    try:
        stats = await kb_to_use.get_stats()
        fact_count = stats.get("total_facts", 0)

        if fact_count == 0:
            logger.info("Knowledge base is empty - returning empty results immediately")
            return {
                "results": [],
                "total_results": 0,
                "query": query,
                "mode": mode,
                "kb_implementation": kb_to_use.__class__.__name__,
                "message": (
                    "Knowledge base is empty - no documents to search. "
                    "Add documents in the Manage tab."
                ),
            }
    except Exception as stats_err:
        logger.warning(f"Could not check KB stats: {stats_err}")

    # FIXED: Check which knowledge base implementation we're using and call with correct parameters
    kb_class_name = kb_to_use.__class__.__name__

    if kb_class_name == "KnowledgeBaseV2":
        # KnowledgeBaseV2 uses 'top_k' parameter
        results = await kb_to_use.search(query=query, top_k=search_limit)
    else:
        # Original KnowledgeBase uses 'similarity_top_k' parameter
        results = await kb_to_use.search(
            query=query, similarity_top_k=search_limit, mode=mode
        )

    # Advanced reranking with cross-encoder if requested
    if enable_reranking and ADVANCED_RAG_AVAILABLE and results:
        try:
            logger.info("Applying advanced reranking to search results")
            rag_service = RAGService(kb_to_use)
            await rag_service.initialize()

            # Rerank results
            reranked_results = await rag_service.rerank_results(query, results)

            return {
                "results": reranked_results,
                "total_results": len(reranked_results),
                "query": query,
                "mode": mode,
                "kb_implementation": kb_class_name,
                "reranking_applied": True,
                "reranking_method": "cross-encoder",
            }
        except Exception as e:
            logger.error(f"Advanced reranking failed: {e}, returning original results")
            # Fall through to regular results

    # Enhanced search with RAG if requested and available (legacy support)
    if use_rag and RAG_AVAILABLE and results:
        try:
            rag_enhancement = await _enhance_search_with_rag(query, results)
            return {
                "results": results,
                "total_results": len(results),
                "query": query,
                "mode": mode,
                "kb_implementation": kb_class_name,
                "rag_enhanced": True,
                "rag_analysis": rag_enhancement,
            }
        except Exception as e:
            logger.error(f"RAG enhancement failed: {e}")
            # Continue with regular results if RAG fails

    return {
        "results": results,
        "total_results": len(results),
        "query": query,
        "mode": mode,
        "kb_implementation": kb_class_name,
        "rag_enhanced": False,
        "reranking_applied": False,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_search",
    error_code_prefix="KB",
)
@router.post("/enhanced_search")
async def enhanced_search(request: EnhancedSearchRequest, req: Request):
    """
    Enhanced search with tag filtering, hybrid mode, and query preprocessing.

    Issue #78: Search Quality Improvements

    Features:
    - Hybrid search mode (semantic + keyword with RRF)
    - Tag-based filtering (match all or any)
    - Query preprocessing (abbreviation expansion)
    - Minimum score threshold
    - Optional cross-encoder reranking
    - Pagination support

    Request body:
    - query: Search query string
    - limit: Maximum results (default: 10, max: 100)
    - offset: Pagination offset (default: 0)
    - category: Optional category filter
    - tags: Optional list of tags to filter by
    - tags_match_any: If True, match ANY tag. If False, match ALL (default: False)
    - mode: "semantic", "keyword", or "hybrid" (default: "hybrid")
    - enable_reranking: Enable cross-encoder reranking (default: False)
    - min_score: Minimum similarity score 0.0-1.0 (default: 0.0)

    Returns:
    - success: Boolean status
    - results: List of search results
    - total_count: Total matching results (before pagination)
    - query_processed: The preprocessed query used
    - mode: Search mode used
    - tags_applied: Tags used for filtering
    - min_score_applied: Minimum score threshold used
    - reranking_applied: Whether reranking was applied
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    # Check if knowledge base supports enhanced_search
    if not hasattr(kb_to_use, "enhanced_search"):
        # Fallback to regular search with limited functionality
        logger.warning("KB implementation does not support enhanced_search, using fallback")
        results = await kb_to_use.search(
            query=request.query,
            top_k=request.limit,
            mode=request.mode if request.mode in VALID_SEARCH_MODES else "auto",
        )
        return {
            "success": True,
            "results": results,
            "total_count": len(results),
            "query_processed": request.query,
            "mode": request.mode,
            "tags_applied": [],
            "min_score_applied": 0.0,
            "reranking_applied": False,
            "message": "Using fallback search - enhanced features not available",
        }

    logger.info(
        f"Enhanced search: '{request.query}' (limit={request.limit}, offset={request.offset}, "
        f"mode={request.mode}, tags={request.tags}, min_score={request.min_score})"
    )

    # Call enhanced_search method
    result = await kb_to_use.enhanced_search(
        query=request.query,
        limit=request.limit,
        offset=request.offset,
        category=request.category,
        tags=request.tags,
        tags_match_any=request.tags_match_any,
        mode=request.mode,
        enable_reranking=request.enable_reranking,
        min_score=request.min_score,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_enhanced_search",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/rag_search")
async def rag_enhanced_search(request: dict, req: Request):
    """RAG-enhanced knowledge search for comprehensive document synthesis"""
    if not RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="RAG functionality not available - AI Stack may not be running",
        )

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "synthesized_response": "",
            "results": [],
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    limit = request.get("limit", 10)
    reformulate_query = request.get("reformulate_query", True)

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    # Use limit if provided, otherwise use top_k
    search_limit = limit if request.get("limit") is not None else top_k

    logger.info(
        f"RAG-enhanced search request: '{query}' "
        f"(top_k={search_limit}, reformulate={reformulate_query})"
    )

    # Check if knowledge base is empty - fast check to avoid timeout
    try:
        stats = await kb_to_use.get_stats()
        fact_count = stats.get("total_facts", 0)

        if fact_count == 0:
            logger.info(
                "Knowledge base is empty - "
                "returning empty RAG results immediately"
            )
            return {
                "status": "success",
                "synthesized_response": (
                    "The knowledge base is currently empty. "
                    "Please add documents in the Manage tab to enable search functionality."
                ),
                "results": [],
                "query": query,
                "reformulated_query": query,
                "rag_analysis": {
                    "relevance_score": 0.0,
                    "confidence": 0.0,
                    "sources_used": 0,
                    "synthesis_quality": "empty_kb",
                },
                "message": "Knowledge base is empty",
            }
    except Exception as stats_err:
        logger.warning(f"Could not check KB stats: {stats_err}")

    # Step 1: Query reformulation if requested
    original_query = query
    reformulated_queries = [query]

    if reformulate_query:
        try:
            rag_agent = get_rag_agent()
            reformulation_result = await rag_agent.reformulate_query(query)

            if reformulation_result.get("status") == "success":
                additional_queries = reformulation_result.get(
                    "reformulated_queries", []
                )
                reformulated_queries.extend(
                    additional_queries[:3]
                )  # Limit to avoid too many queries

        except Exception as e:
            logger.warning(f"Query reformulation failed: {e}")

    # Step 2: Search with all queries
    all_results = []
    seen_content = set()

    for search_query in reformulated_queries:
        try:
            # Get search results
            kb_class_name = kb_to_use.__class__.__name__

            if kb_class_name == "KnowledgeBaseV2":
                query_results = await kb_to_use.search(
                    query=search_query, top_k=search_limit
                )
            else:
                query_results = await kb_to_use.search(
                    query=search_query, similarity_top_k=search_limit
                )

            # Deduplicate results
            for result in query_results:
                content = result.get("content", "")
                if content and content not in seen_content:
                    seen_content.add(content)
                    result["source_query"] = search_query
                    all_results.append(result)

        except Exception as e:
            logger.error(f"Search failed for query '{search_query}': {e}")

    # Step 3: Limit total results
    all_results = all_results[:search_limit]

    # Step 4: RAG processing for synthesis
    if all_results:
        try:
            rag_agent = get_rag_agent()

            # Convert results to RAG-compatible format
            documents = []
            for result in all_results:
                documents.append(
                    {
                        "content": result.get("content", ""),
                        "metadata": {
                            "filename": (
                                result.get("metadata", {}).get("title", "Unknown")
                            ),
                            "source": (
                                result.get("metadata", {}).get(
                                    "source", "knowledge_base"
                                )
                            ),
                            "category": (
                                result.get("metadata", {}).get("category", "general")
                            ),
                            "score": result.get("score", 0.0),
                            "source_query": result.get("source_query", original_query),
                        },
                    }
                )

            # Process with RAG agent
            rag_result = await rag_agent.process_document_query(
                query=original_query,
                documents=documents,
                context={"reformulated_queries": reformulated_queries},
            )

            return {
                "status": "success",
                "synthesized_response": rag_result.get("synthesized_response", ""),
                "confidence_score": rag_result.get("confidence_score", 0.0),
                "document_analysis": rag_result.get("document_analysis", {}),
                "sources_used": rag_result.get("sources_used", []),
                "results": all_results,
                "total_results": len(all_results),
                "original_query": original_query,
                "reformulated_queries": (
                    reformulated_queries[1:] if len(reformulated_queries) > 1 else []
                ),
                "kb_implementation": kb_to_use.__class__.__name__,
                "agent_metadata": rag_result.get("metadata", {}),
                "rag_enhanced": True,
            }

        except Exception as e:
            logger.error(f"RAG processing failed: {e}")
            # Return search results without synthesis
            return {
                "status": "partial_success",
                "synthesized_response": (
                    f"Found {len(all_results)} relevant documents but synthesis failed: {str(e)}"
                ),
                "results": all_results,
                "total_results": len(all_results),
                "original_query": original_query,
                "reformulated_queries": (
                    reformulated_queries[1:] if len(reformulated_queries) > 1 else []
                ),
                "error": str(e),
                "rag_enhanced": False,
            }
    else:
        return {
            "status": "success",
            "synthesized_response": (
                f"No relevant documents found for query: '{original_query}'"
            ),
            "results": [],
            "total_results": 0,
            "original_query": original_query,
            "reformulated_queries": (
                reformulated_queries[1:] if len(reformulated_queries) > 1 else []
            ),
            "rag_enhanced": True,
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="similarity_search",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/similarity_search")
async def similarity_search(request: dict, req: Request):
    """
    Perform similarity search with optional RAG enhancement.
    FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "results": [],
            "total_results": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    threshold = request.get("threshold", 0.7)
    use_rag = request.get("use_rag", False)

    logger.info(
        f"Similarity search request: '{query}' "
        f"(top_k={top_k}, threshold={threshold}, use_rag={use_rag})"
    )

    # FIXED: Check which knowledge base implementation we're using and call with correct parameters
    kb_class_name = kb_to_use.__class__.__name__

    if kb_class_name == "KnowledgeBaseV2":
        # KnowledgeBaseV2 uses 'top_k' parameter
        results = await kb_to_use.search(query=query, top_k=top_k)
    else:
        # Original KnowledgeBase uses 'similarity_top_k' parameter
        results = await kb_to_use.search(query=query, similarity_top_k=top_k)

    # Filter by threshold if specified
    if threshold > 0:
        filtered_results = []
        for result in results:
            if result.get("score", 0) >= threshold:
                filtered_results.append(result)
        results = filtered_results

    # Enhanced search with RAG if requested and available
    if use_rag and RAG_AVAILABLE and results:
        try:
            rag_enhancement = await _enhance_search_with_rag(query, results)
            return {
                "results": results,
                "total_results": len(results),
                "query": query,
                "threshold": threshold,
                "kb_implementation": kb_class_name,
                "rag_enhanced": True,
                "rag_analysis": rag_enhancement,
            }
        except Exception as e:
            logger.error(f"RAG enhancement failed: {e}")
            # Continue with regular results if RAG fails

    return {
        "results": results,
        "total_results": len(results),
        "query": query,
        "threshold": threshold,
        "kb_implementation": kb_class_name,
        "rag_enhanced": False,
    }


# ===== HELPER FUNCTIONS =====


async def _enhance_search_with_rag(
    query: str, results: List[Metadata]
) -> Metadata:
    """Enhance search results with RAG analysis"""
    try:
        rag_agent = get_rag_agent()

        # Convert results to documents for RAG processing
        documents = []
        for result in results:
            documents.append(
                {
                    "content": result.get("content", ""),
                    "metadata": {
                        "filename": result.get("metadata", {}).get("title", "Unknown"),
                        "source": (
                            result.get("metadata", {}).get("source", "knowledge_base")
                        ),
                        "score": result.get("score", 0.0),
                    },
                }
            )

        # Analyze document relevance
        document_analysis = rag_agent._analyze_document_relevance(query, documents)

        # Rank documents
        ranked_documents = await rag_agent.rank_documents(query, documents)

        return {
            "document_analysis": document_analysis,
            "ranked_documents": ranked_documents[:5],  # Top 5 ranked documents
            "analysis_summary": {
                "total_analyzed": len(documents),
                "high_relevance_count": document_analysis.get("high_relevance", 0),
                "medium_relevance_count": document_analysis.get("medium_relevance", 0),
                "low_relevance_count": document_analysis.get("low_relevance", 0),
            },
        }

    except Exception as e:
        logger.error(f"RAG enhancement error: {e}")
        return {
            "error": str(e),
            "analysis_summary": {
                "total_analyzed": len(results),
                "error": "RAG analysis failed",
            },
        }
