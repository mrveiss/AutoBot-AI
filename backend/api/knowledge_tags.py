# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Tag Management API - Tag operations for knowledge base facts.

This module contains all tag-related API endpoints for the knowledge base.
Extracted from knowledge.py for better maintainability (Issue #185, #209).

Endpoints:
- POST /fact/{fact_id}/tags - Add tags to a fact
- DELETE /fact/{fact_id}/tags - Remove tags from a fact
- GET /fact/{fact_id}/tags - Get tags for a fact
- POST /tags/search - Search facts by tags
- GET /tags - List all tags
- POST /tags/bulk - Bulk tag operations

Related Issues: #77 (Tags), #185 (Split), #209 (Knowledge split)
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.knowledge_models import (
    AddTagsRequest,
    BulkTagRequest,
    FactIdValidator,
    RemoveTagsRequest,
    SearchByTagsRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Create router for tag management endpoints
router = APIRouter(tags=["knowledge-tags"])


# ===== TAG MANAGEMENT ENDPOINTS (Issue #77) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_tags_to_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/fact/{fact_id}/tags")
async def add_tags_to_fact(
    fact_id: str = Path(..., description="Fact ID to add tags to"),
    request: AddTagsRequest = ...,
    req: Request = None,
):
    """
    Add tags to a knowledge base fact.

    Parameters:
    - fact_id: UUID of the fact
    - tags: List of tags to add (lowercase, alphanumeric with hyphens/underscores)

    Returns:
    - status: success or error
    - fact_id: ID of the tagged fact
    - tags: Updated list of tags on the fact
    - added_count: Number of new tags added
    """
    # Validate fact_id format
    FactIdValidator(fact_id=fact_id)

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info(f"Adding tags to fact {fact_id}: {request.tags}")

    # Call add_tags method
    result = await kb.add_tags_to_fact(fact_id=fact_id, tags=request.tags)

    if result.get("success"):
        return {
            "status": "success",
            "fact_id": fact_id,
            "tags": result.get("tags", []),
            "added_count": result.get("added_count", 0),
            "message": result.get("message", "Tags added successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        else:
            raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_tags_from_fact",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/fact/{fact_id}/tags")
async def remove_tags_from_fact(
    fact_id: str = Path(..., description="Fact ID to remove tags from"),
    request: RemoveTagsRequest = ...,
    req: Request = None,
):
    """
    Remove tags from a knowledge base fact.

    Parameters:
    - fact_id: UUID of the fact
    - tags: List of tags to remove

    Returns:
    - status: success or error
    - fact_id: ID of the fact
    - tags: Remaining tags on the fact
    - removed_count: Number of tags removed
    """
    # Validate fact_id format
    FactIdValidator(fact_id=fact_id)

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info(f"Removing tags from fact {fact_id}: {request.tags}")

    # Call remove_tags method
    result = await kb.remove_tags_from_fact(fact_id=fact_id, tags=request.tags)

    if result.get("success"):
        return {
            "status": "success",
            "fact_id": fact_id,
            "tags": result.get("tags", []),
            "removed_count": result.get("removed_count", 0),
            "message": result.get("message", "Tags removed successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        else:
            raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_tags",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/fact/{fact_id}/tags")
async def get_fact_tags(
    fact_id: str = Path(..., description="Fact ID to get tags for"),
    req: Request = None,
):
    """
    Get all tags for a specific fact.

    Parameters:
    - fact_id: UUID of the fact

    Returns:
    - fact_id: ID of the fact
    - tags: List of tags on the fact
    """
    # Validate fact_id format
    FactIdValidator(fact_id=fact_id)

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_fact_tags(fact_id=fact_id)

    if result.get("success"):
        return {
            "status": "success",
            "fact_id": fact_id,
            "tags": result.get("tags", []),
        }
    else:
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        else:
            raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_facts_by_tags",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/tags/search")
async def search_facts_by_tags(
    request: SearchByTagsRequest,
    req: Request = None,
):
    """
    Search for facts by tags.

    Parameters:
    - tags: List of tags to search for
    - match_all: If True, facts must have ALL tags. If False, facts with ANY tag match.
    - limit: Maximum number of results (default: 50)
    - offset: Pagination offset (default: 0)
    - category: Optional category filter

    Returns:
    - facts: List of matching facts with their metadata
    - total_count: Total number of matching facts
    - tags_searched: Tags used in the search
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info(
        f"Searching facts by tags: {request.tags}, match_all={request.match_all}"
    )

    result = await kb.search_facts_by_tags(
        tags=request.tags,
        match_all=request.match_all,
        limit=request.limit,
        offset=request.offset,
        category=request.category,
    )

    return {
        "status": "success",
        "facts": result.get("facts", []),
        "total_count": result.get("total_count", 0),
        "tags_searched": request.tags,
        "match_all": request.match_all,
        "limit": request.limit,
        "offset": request.offset,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_all_tags",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/tags")
async def list_all_tags(
    limit: int = Query(default=100, ge=1, le=1000),
    prefix: Optional[str] = Query(default=None, max_length=50),
    req: Request = None,
):
    """
    List all unique tags in the knowledge base.

    Parameters:
    - limit: Maximum number of tags to return (default: 100)
    - prefix: Optional prefix filter (e.g., 'sec' returns 'security', 'secret', etc.)

    Returns:
    - tags: List of unique tags with usage counts
    - total_count: Total number of unique tags
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    # Validate prefix if provided
    if prefix:
        prefix = prefix.lower().strip()
        if not re.match(r"^[a-z0-9_-]*$", prefix):
            raise HTTPException(
                status_code=400,
                detail="Invalid prefix format: only lowercase alphanumeric allowed",
            )

    result = await kb.list_all_tags(limit=limit, prefix=prefix)

    return {
        "status": "success",
        "tags": result.get("tags", []),
        "total_count": result.get("total_count", 0),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="bulk_tag_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/tags/bulk")
async def bulk_tag_facts(
    request: BulkTagRequest,
    req: Request = None,
):
    """
    Apply or remove tags from multiple facts at once.

    Parameters:
    - fact_ids: List of fact IDs to tag (max 100)
    - tags: List of tags to apply/remove (max 20)
    - operation: 'add' or 'remove'

    Returns:
    - status: success or partial_success
    - processed_count: Number of facts processed
    - failed_count: Number of facts that failed
    - results: Per-fact results
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info(
        f"Bulk {request.operation} tags: {len(request.fact_ids)} facts, "
        f"{len(request.tags)} tags"
    )

    result = await kb.bulk_tag_facts(
        fact_ids=request.fact_ids,
        tags=request.tags,
        operation=request.operation,
    )

    return {
        "status": result.get("status", "success"),
        "operation": request.operation,
        "processed_count": result.get("processed_count", 0),
        "failed_count": result.get("failed_count", 0),
        "results": result.get("results", []),
    }
