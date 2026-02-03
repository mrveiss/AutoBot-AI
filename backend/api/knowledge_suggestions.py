# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base ML-Based Suggestions API Router

Issue #413: Provides API endpoints for tag and category suggestions
based on content similarity using existing embeddings.

Endpoints:
- POST /suggestions/tags - Suggest tags for content
- POST /suggestions/categories - Suggest categories for content
- POST /suggestions/all - Suggest both tags and categories
- POST /facts/{fact_id}/auto-apply - Auto-apply suggestions to fact
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.knowledge_models import (
    AutoApplySuggestionsRequest,
    SuggestAllRequest,
    SuggestCategoriesRequest,
    SuggestTagsRequest,
)
from src.knowledge import get_knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-suggestions"])


@router.post("/suggestions/tags")
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggestions/categories")
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggestions/all")
async def suggest_all(request: SuggestAllRequest):
    """
    Suggest both tags and categories in a single call.

    More efficient than calling /suggestions/tags and /suggestions/categories
    separately as it only performs one similarity search.

    Args:
        request: SuggestAllRequest with content and limits

    Returns:
        Dict with:
        - success: bool
        - tag_suggestions: List of {tag, confidence, source_count}
        - category_suggestions: List of {category_path, confidence, source_count}
        - similar_docs_analyzed: int

    Example:
        POST /api/knowledge_base/suggestions/all
        {
            "content": "Docker container orchestration with Kubernetes...",
            "tag_limit": 5,
            "category_limit": 3
        }

        Response:
        {
            "success": true,
            "tag_suggestions": [
                {"tag": "docker", "confidence": 0.95, "source_count": 12},
                {"tag": "kubernetes", "confidence": 0.91, "source_count": 10}
            ],
            "category_suggestions": [
                {"category_path": "tech/devops", "confidence": 0.89, "source_count": 8}
            ],
            "similar_docs_analyzed": 20
        }
    """
    try:
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Combined suggestion failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/facts/{fact_id}/auto-apply")
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
        # Basic fact_id validation
        if not fact_id or len(fact_id) > 255:
            raise HTTPException(status_code=400, detail="Invalid fact_id")

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

        logger.info(
            "Auto-applied %d tags and category=%s to fact %s",
            len(result.get("applied_tags", [])),
            result.get("applied_category"),
            fact_id,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Auto-apply suggestions failed for %s: %s", fact_id, e)
        raise HTTPException(status_code=500, detail=str(e))
