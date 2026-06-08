# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base ML-Based Suggestions API Router

Issue #413: Provides API endpoints for tag and category suggestions
based on content similarity using existing embeddings.

Issue #3284: Adds context-based document suggestions ranked by relevance
and recency, with preview snippets.

Endpoints:
- POST /suggestions/tags - Suggest tags for content
- POST /suggestions/categories - Suggest categories for content
- POST /suggestions/all - Suggest both tags and categories
- POST /suggestions/context - Suggest KB documents relevant to conversation context
- POST /facts/{fact_id}/auto-apply - Auto-apply suggestions to fact
"""

from fastapi import APIRouter, HTTPException

from api.schemas_knowledge import (
    AutoApplySuggestionsRequest,
    ContextSuggestionsRequest,
    KnowledgeAutoApplySuggestionsResponse,
    KnowledgeSuggestionsAllResponse,
    KnowledgeSuggestionsCategoriesResponse,
    KnowledgeSuggestionsContextResponse,
    KnowledgeSuggestionsTagsResponse,
    SuggestAllRequest,
    SuggestCategoriesRequest,
    SuggestTagsRequest,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge import get_knowledge_base

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge-suggestions"])


@router.post("/suggestions/tags", response_model=KnowledgeSuggestionsTagsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="suggest_tags",
    error_code_prefix="KNOWLEDGE_SUGGESTIONS",
)
async def suggest_tags(request: SuggestTagsRequest):
    """
    Suggest tags for content based on similar documents.

    Uses embedding-based similarity to find related documents in the knowledge
    base and extracts tags from them, weighted by similarity score.

    Args:
        request: SuggestTagsRequest with content to analyze

    Returns:
        Dict with:
        - success: bool
        - suggestions: List of {tag, confidence, source_count}
        - similar_docs_analyzed: int

    Example:
        POST /api/knowledge_base/suggestions/tags
        {
            "content": "Python security best practices for web applications...",
            "limit": 5,
            "min_confidence": 0.3
        }

        Response:
        {
            "success": true,
            "suggestions": [
                {"tag": "python", "confidence": 0.92, "source_count": 8},
                {"tag": "security", "confidence": 0.85, "source_count": 5},
                {"tag": "web", "confidence": 0.72, "source_count": 3}
            ],
            "similar_docs_analyzed": 20
        }
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.suggest_tags(
            content=request.content,
            limit=request.limit,
            min_confidence=request.min_confidence,
            similarity_limit=request.similarity_limit,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate suggestions"),
            )

        logger.info(
            "Generated %d tag suggestions for content (len=%d)",
            len(result.get("suggestions", [])),
            len(request.content),
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Tag suggestion failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/suggestions/categories", response_model=KnowledgeSuggestionsCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="suggest_categories",
    error_code_prefix="KNOWLEDGE_SUGGESTIONS",
)
async def suggest_categories(request: SuggestCategoriesRequest):
    """
    Suggest categories for content based on similar documents.

    Uses embedding-based similarity to find related documents and
    extract categories weighted by similarity score.

    Args:
        request: SuggestCategoriesRequest with content to analyze

    Returns:
        Dict with:
        - success: bool
        - suggestions: List of {category_path, confidence, source_count}
        - similar_docs_analyzed: int

    Example:
        POST /api/knowledge_base/suggestions/categories
        {
            "content": "Machine learning model training with TensorFlow...",
            "limit": 3
        }

        Response:
        {
            "success": true,
            "suggestions": [
                {"category_path": "tech/ai/ml", "confidence": 0.88, "source_count": 6},
                {"category_path": "tech/python", "confidence": 0.65, "source_count": 3}
            ],
            "similar_docs_analyzed": 20
        }
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.suggest_categories(
            content=request.content,
            limit=request.limit,
            min_confidence=request.min_confidence,
            similarity_limit=request.similarity_limit,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate suggestions"),
            )

        logger.info(
            "Generated %d category suggestions for content (len=%d)",
            len(result.get("suggestions", [])),
            len(request.content),
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Category suggestion failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


async def _call_kb_suggest_all(request: "SuggestAllRequest") -> dict:
    """Helper for suggest_all. Ref: #1088."""
    kb = await get_knowledge_base()
    result = await kb.suggest_all(
        content=request.content,
        tag_limit=request.tag_limit,
        category_limit=request.category_limit,
        min_confidence=request.min_confidence,
        similarity_limit=request.similarity_limit,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Failed to generate suggestions"),
        )
    logger.info(
        "Generated %d tag + %d category suggestions for content (len=%d)",
        len(result.get("tag_suggestions", [])),
        len(result.get("category_suggestions", [])),
        len(request.content),
    )
    return result


@router.post("/suggestions/all", response_model=KnowledgeSuggestionsAllResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="suggest_all",
    error_code_prefix="KNOWLEDGE_SUGGESTIONS",
)
async def suggest_all(request: SuggestAllRequest):
    """Suggest both tags and categories in a single call.

    More efficient than calling /suggestions/tags and /suggestions/categories
    separately as it only performs one similarity search.
    POST /api/knowledge_base/suggestions/all
    Returns: {success, tag_suggestions, category_suggestions, similar_docs_analyzed}
    """
    try:
        return await _call_kb_suggest_all(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Combined suggestion failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/suggestions/context", response_model=KnowledgeSuggestionsContextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="suggest_by_context",
    error_code_prefix="KNOWLEDGE_SUGGESTIONS",
)
async def suggest_by_context(request: ContextSuggestionsRequest):
    """
    Suggest KB documents relevant to the current conversation context (Issue #3284).

    Performs a semantic similarity search against the knowledge base using the
    provided context, then ranks results by a weighted combination of relevance
    score and recency (configurable via recency_weight).

    Each suggestion includes a short preview snippet so the UI can display
    meaningful context without fetching the full document.

    Args:
        request: ContextSuggestionsRequest

    Returns:
        Dict with:
        - success: bool
        - suggestions: List of ranked suggestion objects, each containing:
            - fact_id, title, snippet, relevance_score, recency_score,
              combined_score, tags, category, created_at
        - total_candidates: Number of documents examined before filtering

    Example:
        POST /api/knowledge_base/suggestions/context
        {
            "context": "How do I configure Redis connection pooling in FastAPI?",
            "limit": 5,
            "recency_weight": 0.2,
            "min_score": 0.3,
            "snippet_length": 200
        }

        Response:
        {
            "success": true,
            "suggestions": [
                {
                    "fact_id": "abc123",
                    "title": "Redis connection pooling guide",
                    "snippet": "Connection pooling in Redis can be configured...",
                    "relevance_score": 0.87,
                    "recency_score": 0.95,
                    "combined_score": 0.885,
                    "tags": ["redis", "fastapi", "performance"],
                    "category": "tech/databases",
                    "created_at": "2025-03-15T10:30:00+00:00"
                }
            ],
            "total_candidates": 18
        }
    """
    try:
        kb = await get_knowledge_base()
        result = await kb.suggest_by_context(
            context=request.context,
            limit=request.limit,
            recency_weight=request.recency_weight,
            min_score=request.min_score,
            snippet_length=request.snippet_length,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to generate context suggestions"),
            )

        logger.info(
            "Context suggestions: returned %d suggestions (context_len=%d)",
            len(result.get("suggestions", [])),
            len(request.context),
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Context suggestion failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


def _validate_fact_id(fact_id: str) -> None:
    """Helper for auto_apply_suggestions. Ref: #1088."""
    if not fact_id or len(fact_id) > 255:
        raise HTTPException(status_code=400, detail="Invalid fact_id")


async def _call_auto_apply_kb(fact_id: str, request: AutoApplySuggestionsRequest) -> dict:
    """Helper for auto_apply_suggestions. Ref: #1088."""
    kb = await get_knowledge_base()
    result = await kb.auto_apply_suggestions(
        fact_id=fact_id,
        content=request.content,
        apply_tags=request.apply_tags,
        apply_category=request.apply_category,
        min_confidence=request.min_confidence,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Failed to auto-apply suggestions"),
        )
    return result


def _log_auto_apply_result(fact_id: str, result: dict) -> None:
    """Helper for auto_apply_suggestions. Ref: #1088."""
    logger.info(
        "Auto-applied %d tags and category=%s to fact %s",
        len(result.get("applied_tags", [])),
        result.get("applied_category"),
        fact_id,
    )


@router.post("/facts/{fact_id}/auto-apply", response_model=KnowledgeAutoApplySuggestionsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="auto_apply_suggestions",
    error_code_prefix="KNOWLEDGE_SUGGESTIONS",
)
async def auto_apply_suggestions(fact_id: str, request: AutoApplySuggestionsRequest):
    """
    Automatically apply high-confidence suggestions to a fact.

    Analyzes the provided content, generates suggestions, and applies
    those that meet the minimum confidence threshold to the specified fact.

    Args:
        fact_id: The fact ID to apply suggestions to
        request: AutoApplySuggestionsRequest with content and options

    Returns:
        Dict with:
        - success: bool
        - fact_id: str
        - applied_tags: List of tags that were applied
        - applied_category: Category that was applied (or None)
        - skipped_tags: Tags below confidence threshold
        - skipped_categories: Categories below confidence threshold

    Example:
        POST /api/knowledge_base/facts/abc123/auto-apply
        {
            "content": "Python web security tutorial...",
            "apply_tags": true,
            "apply_category": true,
            "min_confidence": 0.85
        }

        Response:
        {
            "success": true,
            "fact_id": "abc123",
            "applied_tags": ["python", "security"],
            "applied_category": "tech/python",
            "skipped_tags": [
                {"tag": "web", "confidence": 0.72}
            ],
            "skipped_categories": []
        }
    """
    try:
        _validate_fact_id(fact_id)
        result = await _call_auto_apply_kb(fact_id, request)
        _log_auto_apply_result(fact_id, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auto-apply suggestions failed for %s: %s", fact_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")
