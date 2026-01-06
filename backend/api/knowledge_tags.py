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
- PUT /tags/{tag_name} - Rename a tag globally (Issue #409)
- DELETE /tags/{tag_name} - Delete a tag globally (Issue #409)
- POST /tags/merge - Merge multiple tags into one (Issue #409)
- GET /tags/{tag_name}/facts - Get all facts with a specific tag (Issue #409)
- GET /tags/{tag_name}/info - Get tag information (Issue #409)
- PATCH /tags/{tag_name}/style - Update tag styling (Issue #410)
- GET /tags/{tag_name}/style - Get tag style (Issue #410)
- DELETE /tags/{tag_name}/style - Reset tag style to defaults (Issue #410)

Related Issues: #77 (Tags), #185 (Split), #209 (Knowledge split), #409 (Tag CRUD), #410 (Tag Styling)
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query
from src.constants.threshold_constants import QueryDefaults, Request

from backend.api.knowledge_models import (
    AddTagsRequest,
    BulkTagRequest,
    FactIdValidator,
    MergeTagsRequest,
    RemoveTagsRequest,
    RenameTagRequest,
    SearchByTagsRequest,
    UpdateTagStyleRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex for tag prefix validation
_TAG_PREFIX_RE = re.compile(r"^[a-z0-9_-]*$")

# Create router for tag management endpoints
router = APIRouter(tags=["knowledge-tags"])


def _raise_kb_error(error_message: str, default_code: int = 500) -> None:
    """Raise appropriate HTTPException based on error message (#624)."""
    error_lower = error_message.lower()
    if "not found" in error_lower:
        raise HTTPException(status_code=404, detail=error_message)
    raise HTTPException(status_code=default_code, detail=error_message)


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

    logger.info("Adding tags to fact %s: %s", fact_id, request.tags)

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
        _raise_kb_error(result.get("message", "Unknown error"))


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

    logger.info("Removing tags from fact %s: %s", fact_id, request.tags)

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
        _raise_kb_error(result.get("message", "Unknown error"))


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
        _raise_kb_error(result.get("message", "Unknown error"))


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
        if not _TAG_PREFIX_RE.match(prefix):
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


# ===== TAG CRUD OPERATIONS (Issue #409) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rename_tag",
    error_code_prefix="KNOWLEDGE",
)
@router.put("/tags/{tag_name}")
async def rename_tag(
    tag_name: str = Path(..., description="Current tag name to rename"),
    request: RenameTagRequest = ...,
    req: Request = None,
):
    """
    Rename a tag globally across all facts.

    Issue #409: Tag management CRUD operations.

    Parameters:
    - tag_name: Current name of the tag (path parameter)
    - new_tag: New name for the tag (request body)

    Returns:
    - status: success or error
    - old_tag: Previous tag name
    - new_tag: New tag name
    - affected_count: Number of facts updated
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Renaming tag '%s' to '%s'", tag_name, request.new_tag)

    result = await kb.rename_tag(old_tag=tag_name, new_tag=request.new_tag)

    if result.get("success"):
        return {
            "status": "success",
            "old_tag": result.get("old_tag", tag_name),
            "new_tag": result.get("new_tag", request.new_tag),
            "affected_count": result.get("affected_count", 0),
            "message": result.get("message", "Tag renamed successfully"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_tag_globally",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/tags/{tag_name}")
async def delete_tag_globally(
    tag_name: str = Path(..., description="Tag name to delete"),
    req: Request = None,
):
    """
    Delete a tag from all facts globally.

    Issue #409: Tag management CRUD operations.

    Parameters:
    - tag_name: Name of the tag to delete

    Returns:
    - status: success or error
    - tag: Deleted tag name
    - affected_count: Number of facts that had the tag removed
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Deleting tag '%s' globally", tag_name)

    result = await kb.delete_tag_globally(tag=tag_name)

    if result.get("success"):
        return {
            "status": "success",
            "tag": result.get("tag", tag_name),
            "affected_count": result.get("affected_count", 0),
            "message": result.get("message", "Tag deleted successfully"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="merge_tags",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/tags/merge")
async def merge_tags(
    request: MergeTagsRequest,
    req: Request = None,
):
    """
    Merge multiple source tags into a single target tag.

    Issue #409: Tag management CRUD operations.

    All facts with any of the source tags will have those tags replaced
    with the target tag. Source tags are deleted after merge.

    Parameters:
    - source_tags: List of tags to merge (will be removed)
    - target_tag: Target tag to merge into

    Returns:
    - status: success or error
    - source_tags: Tags that were merged
    - target_tag: Target tag
    - affected_count: Number of facts updated
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info(
        "Merging tags %s into '%s'", request.source_tags, request.target_tag
    )

    result = await kb.merge_tags(
        source_tags=request.source_tags,
        target_tag=request.target_tag,
    )

    if result.get("success"):
        return {
            "status": "success",
            "source_tags": result.get("source_tags", request.source_tags),
            "target_tag": result.get("target_tag", request.target_tag),
            "affected_count": result.get("affected_count", 0),
            "message": result.get("message", "Tags merged successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        raise HTTPException(status_code=400, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_by_tag",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/tags/{tag_name}/facts")
async def get_facts_by_tag(
    tag_name: str = Path(..., description="Tag name to get facts for"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=QueryDefaults.DEFAULT_OFFSET, ge=0),
    include_content: bool = Query(default=False),
    req: Request = None,
):
    """
    Get all facts with a specific tag.

    Issue #409: Tag management CRUD operations.

    Parameters:
    - tag_name: Tag to search for
    - limit: Maximum number of facts to return (default: 50, max: 500)
    - offset: Pagination offset (default: 0)
    - include_content: Whether to include fact content (default: False)

    Returns:
    - status: success or error
    - tag: Tag name searched
    - facts: List of facts with the tag
    - total_count: Total number of facts with this tag
    - has_more: Whether more facts are available
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_facts_by_tag(
        tag=tag_name,
        limit=limit,
        offset=offset,
        include_content=include_content,
    )

    if result.get("success"):
        return {
            "status": "success",
            "tag": result.get("tag", tag_name),
            "facts": result.get("facts", []),
            "total_count": result.get("total_count", 0),
            "returned_count": result.get("returned_count", 0),
            "limit": limit,
            "offset": offset,
            "has_more": result.get("has_more", False),
        }
    else:
        error_message = result.get("message", "Unknown error")
        raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_tag_info",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/tags/{tag_name}/info")
async def get_tag_info(
    tag_name: str = Path(..., description="Tag name to get info for"),
    req: Request = None,
):
    """
    Get detailed information about a specific tag.

    Issue #409: Tag management CRUD operations.

    Parameters:
    - tag_name: Tag to get information for

    Returns:
    - status: success or error
    - tag: Tag name
    - fact_count: Number of facts with this tag
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_tag_info(tag=tag_name)

    if result.get("success"):
        return {
            "status": "success",
            "tag": result.get("tag", tag_name),
            "fact_count": result.get("fact_count", 0),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


# ===== TAG STYLING OPERATIONS (Issue #410) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_tag_style",
    error_code_prefix="KNOWLEDGE",
)
@router.patch("/tags/{tag_name}/style")
async def update_tag_style(
    tag_name: str = Path(..., description="Tag name to update styling for"),
    request: UpdateTagStyleRequest = ...,
    req: Request = None,
):
    """
    Update styling for a tag (color, icon, description).

    Issue #410: Tag styling - colors and visual customization.

    Parameters:
    - tag_name: Name of the tag to style
    - color: Hex color code (e.g., '#3B82F6')
    - icon: Optional icon identifier
    - description: Optional tag description

    Returns:
    - status: success or error
    - tag: Tag name
    - style: Updated style information
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info(
        "Updating style for tag '%s': color=%s, icon=%s",
        tag_name,
        request.color,
        request.icon,
    )

    result = await kb.update_tag_style(
        tag=tag_name,
        color=request.color,
        icon=request.icon,
        description=request.description,
    )

    if result.get("success"):
        return {
            "status": "success",
            "tag": result.get("tag", tag_name),
            "style": result.get("style", {}),
            "message": result.get("message", "Tag style updated successfully"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_tag_style",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/tags/{tag_name}/style")
async def get_tag_style(
    tag_name: str = Path(..., description="Tag name to get styling for"),
    req: Request = None,
):
    """
    Get styling information for a tag.

    Issue #410: Tag styling - colors and visual customization.

    Returns default color if no custom style is set.

    Parameters:
    - tag_name: Name of the tag

    Returns:
    - status: success or error
    - tag: Tag name
    - style: Style information (color, icon, description, is_default)
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_tag_style(tag=tag_name)

    if result.get("success"):
        return {
            "status": "success",
            "tag": result.get("tag", tag_name),
            "style": {
                "color": result.get("color"),
                "icon": result.get("icon"),
                "description": result.get("description"),
                "is_default": result.get("is_default", True),
            },
        }
    else:
        error_message = result.get("message", "Unknown error")
        raise HTTPException(status_code=500, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_tag_style",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/tags/{tag_name}/style")
async def delete_tag_style(
    tag_name: str = Path(..., description="Tag name to reset styling for"),
    req: Request = None,
):
    """
    Delete custom styling for a tag (reset to defaults).

    Issue #410: Tag styling - colors and visual customization.

    After deletion, the tag will use a deterministic default color.

    Parameters:
    - tag_name: Name of the tag

    Returns:
    - status: success or error
    - tag: Tag name
    - message: Confirmation message
    """
    # Validate tag format
    tag_name = tag_name.lower().strip()
    if not _TAG_PREFIX_RE.match(tag_name):
        raise HTTPException(
            status_code=400,
            detail="Invalid tag format: only lowercase alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Deleting style for tag '%s'", tag_name)

    result = await kb.delete_tag_style(tag=tag_name)

    if result.get("success"):
        return {
            "status": "success",
            "tag": result.get("tag", tag_name),
            "message": result.get("message", "Tag style reset to defaults"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        raise HTTPException(status_code=500, detail=error_message)
