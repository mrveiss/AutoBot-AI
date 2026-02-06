# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Category Management API - Hierarchical category operations (Issue #411).

This module contains all category-related API endpoints for the knowledge base.

Endpoints:
- POST /categories - Create a new category
- GET /categories/tree - Get full category tree structure
- GET /categories/{category_id} - Get single category
- GET /categories/path/{path} - Get category by path
- PUT /categories/{category_id} - Update category
- DELETE /categories/{category_id} - Delete category
- GET /categories/{category_id}/children - Get immediate children
- GET /categories/{category_id}/ancestors - Get ancestor chain (breadcrumb)
- GET /categories/{category_id}/facts - Get facts in category
- POST /facts/{fact_id}/category - Assign fact to category
- POST /categories/search - Search categories by path pattern

Related Issues: #77 (Organization), #411 (Categories)
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request

from backend.api.knowledge_models import (
    AssignFactToCategoryRequest,
    CreateCategoryRequest,
    SearchCategoriesByPathRequest,
    UpdateCategoryRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
from constants.threshold_constants import QueryDefaults
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Issue #411: Pre-compiled regex for category ID validation
_CATEGORY_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Create router for category management endpoints
router = APIRouter(tags=["knowledge-categories"])


def _raise_kb_error(error_message: str, default_code: int = 500) -> None:
    """Raise appropriate HTTPException based on error message (#624)."""
    error_lower = error_message.lower()
    if "not found" in error_lower:
        raise HTTPException(status_code=404, detail=error_message)
    if "already exists" in error_lower or "has children" in error_lower:
        raise HTTPException(status_code=409, detail=error_message)
    raise HTTPException(status_code=default_code, detail=error_message)


# ===== CATEGORY CRUD OPERATIONS (Issue #411) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_category",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/categories")
async def create_category(
    request: CreateCategoryRequest,
    req: Request = None,
):
    """
    Create a new category in the hierarchy.

    Issue #411: Hierarchical category tree structure.

    Parameters:
    - name: Category name (lowercase, alphanumeric, hyphens, underscores)
    - parent_id: Optional parent category ID (None = root category)
    - description: Optional category description
    - icon: Optional icon identifier
    - color: Optional hex color code

    Returns:
    - status: success or error
    - category: Created category data with ID and path
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Creating category '%s' (parent: %s)", request.name, request.parent_id)

    result = await kb.create_category(
        name=request.name,
        parent_id=request.parent_id,
        description=request.description,
        icon=request.icon,
        color=request.color,
    )

    if result.get("success"):
        return {
            "status": "success",
            "category": result.get("category"),
            "message": result.get("message", "Category created successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        if "already exists" in error_message.lower():
            raise HTTPException(status_code=409, detail=error_message)
        elif "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        else:
            raise HTTPException(status_code=400, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_category_tree",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/tree")
async def get_category_tree(
    root_id: Optional[str] = Query(
        default=None, description="Start from specific category"
    ),
    max_depth: int = Query(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=20,
        description="Maximum tree depth",
    ),
    include_fact_counts: bool = Query(default=True, description="Include fact counts"),
    req: Request = None,
):
    """
    Get the full category tree structure.

    Issue #411: Recursive tree building for API response.

    Parameters:
    - root_id: Optional root to start from (None = full tree)
    - max_depth: Maximum depth to traverse
    - include_fact_counts: Include fact counts in each node

    Returns:
    - status: success or error
    - tree: Nested tree structure with children arrays
    - total_categories: Total number of categories
    """
    # Validate root_id if provided
    if root_id:
        root_id = root_id.strip()
        if not _CATEGORY_ID_RE.match(root_id):
            raise HTTPException(
                status_code=400,
                detail="Invalid root_id format: only alphanumeric, hyphens, underscores",
            )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_category_tree(
        root_id=root_id,
        max_depth=max_depth,
        include_fact_counts=include_fact_counts,
    )

    if result.get("success"):
        return {
            "status": "success",
            "tree": result.get("tree", []),
            "total_categories": result.get("total_categories", 0),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_category",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/{category_id}")
async def get_category(
    category_id: str = Path(..., description="Category UUID"),
    req: Request = None,
):
    """
    Get a single category by ID.

    Issue #411: Hierarchical category tree structure.

    Parameters:
    - category_id: Category UUID

    Returns:
    - status: success or error
    - category: Category data
    """
    # Validate category_id format
    category_id = category_id.strip()
    if not _CATEGORY_ID_RE.match(category_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid category_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_category(category_id=category_id)

    if result.get("success"):
        return {
            "status": "success",
            "category": result.get("category"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_category_by_path",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/path/{path:path}")
async def get_category_by_path(
    path: str = Path(..., description="Category path (e.g., 'tech/python/async')"),
    req: Request = None,
):
    """
    Get a category by its path.

    Issue #411: Path-based category lookups.

    Parameters:
    - path: Category path (e.g., "tech/python/async")

    Returns:
    - status: success or error
    - category: Category data
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_category_by_path(path=path)

    if result.get("success"):
        return {
            "status": "success",
            "category": result.get("category"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_category",
    error_code_prefix="KNOWLEDGE",
)
@router.put("/categories/{category_id}")
async def update_category(
    category_id: str = Path(..., description="Category UUID"),
    request: UpdateCategoryRequest = ...,
    req: Request = None,
):
    """
    Update category metadata.

    Issue #411: Category CRUD operations.

    Note: Renaming updates the path and all child paths.

    Parameters:
    - category_id: Category UUID
    - name: New name (triggers path update)
    - description: New description
    - icon: New icon identifier
    - color: New hex color code

    Returns:
    - status: success or error
    - category: Updated category data
    """
    # Validate category_id format
    category_id = category_id.strip()
    if not _CATEGORY_ID_RE.match(category_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid category_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Updating category '%s'", category_id)

    result = await kb.update_category(
        category_id=category_id,
        name=request.name,
        description=request.description,
        icon=request.icon,
        color=request.color,
    )

    if result.get("success"):
        return {
            "status": "success",
            "category": result.get("category"),
            "message": result.get("message", "Category updated successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        elif "already exists" in error_message.lower():
            raise HTTPException(status_code=409, detail=error_message)
        else:
            raise HTTPException(status_code=400, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_category",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: str = Path(..., description="Category UUID"),
    recursive: bool = Query(default=False, description="Delete descendants"),
    reassign_to: Optional[str] = Query(default=None, description="Reassign facts to"),
    req: Request = None,
):
    """
    Delete a category.

    Issue #411: Category deletion with child handling.

    Parameters:
    - category_id: Category UUID to delete
    - recursive: If True, delete all descendants. If False, fail if has children.
    - reassign_to: Optional category ID to reassign facts to

    Returns:
    - status: success or error
    - deleted_count: Number of categories deleted
    - facts_reassigned: Number of facts reassigned
    """
    # Validate category_id format
    category_id = category_id.strip()
    if not _CATEGORY_ID_RE.match(category_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid category_id format: only alphanumeric, hyphens, underscores",
        )

    # Validate reassign_to if provided
    if reassign_to:
        reassign_to = reassign_to.strip()
        if not _CATEGORY_ID_RE.match(reassign_to):
            raise HTTPException(
                status_code=400,
                detail="Invalid reassign_to format: only alphanumeric, hyphens, underscores",
            )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Deleting category '%s' (recursive=%s)", category_id, recursive)

    result = await kb.delete_category(
        category_id=category_id,
        recursive=recursive,
        reassign_to=reassign_to,
    )

    if result.get("success"):
        return {
            "status": "success",
            "deleted_count": result.get("deleted_count", 0),
            "facts_reassigned": result.get("facts_reassigned", 0),
            "message": result.get("message", "Category deleted successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        if "not found" in error_message.lower():
            raise HTTPException(status_code=404, detail=error_message)
        elif "has children" in error_message.lower():
            raise HTTPException(status_code=409, detail=error_message)
        else:
            raise HTTPException(status_code=400, detail=error_message)


# ===== CATEGORY HIERARCHY OPERATIONS (Issue #411) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_category_children",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/{category_id}/children")
async def get_category_children(
    category_id: str = Path(..., description="Parent category UUID"),
    req: Request = None,
):
    """
    Get immediate children of a category.

    Issue #411: Tree navigation.

    Parameters:
    - category_id: Parent category UUID

    Returns:
    - status: success or error
    - children: List of child categories
    - count: Number of children
    """
    # Validate category_id format
    category_id = category_id.strip()
    if not _CATEGORY_ID_RE.match(category_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid category_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_children(category_id=category_id)

    if result.get("success"):
        return {
            "status": "success",
            "parent_id": result.get("parent_id"),
            "children": result.get("children", []),
            "count": result.get("count", 0),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_category_ancestors",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/{category_id}/ancestors")
async def get_category_ancestors(
    category_id: str = Path(..., description="Category UUID"),
    req: Request = None,
):
    """
    Get all ancestors of a category (breadcrumb trail).

    Issue #411: Breadcrumb navigation.

    Parameters:
    - category_id: Category UUID

    Returns:
    - status: success or error
    - ancestors: List from root to immediate parent
    - depth: Number of ancestors
    """
    # Validate category_id format
    category_id = category_id.strip()
    if not _CATEGORY_ID_RE.match(category_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid category_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_ancestors(category_id=category_id)

    if result.get("success"):
        return {
            "status": "success",
            "category_id": result.get("category_id"),
            "ancestors": result.get("ancestors", []),
            "depth": result.get("depth", 0),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


# ===== CATEGORY-FACT OPERATIONS (Issue #411) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_in_category",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/{category_id}/facts")
async def get_facts_in_category(
    category_id: str = Path(..., description="Category UUID"),
    include_descendants: bool = Query(
        default=False, description="Include facts from children"
    ),
    limit: int = Query(default=QueryDefaults.DEFAULT_PAGE_SIZE, ge=1, le=500),
    offset: int = Query(default=QueryDefaults.DEFAULT_OFFSET, ge=0),
    req: Request = None,
):
    """
    Get all facts in a category.

    Issue #411: Retrieve facts by category.

    Parameters:
    - category_id: Category UUID
    - include_descendants: Include facts from child categories
    - limit: Maximum number of facts
    - offset: Pagination offset

    Returns:
    - status: success or error
    - facts: List of facts
    - total_count: Total facts in category
    """
    # Validate category_id format
    category_id = category_id.strip()
    if not _CATEGORY_ID_RE.match(category_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid category_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_facts_in_category(
        category_id=category_id,
        include_descendants=include_descendants,
        limit=limit,
        offset=offset,
    )

    if result.get("success"):
        return {
            "status": "success",
            "category_id": result.get("category_id"),
            "category_path": result.get("category_path"),
            "facts": result.get("facts", []),
            "total_count": result.get("total_count", 0),
            "returned_count": result.get("returned_count", 0),
            "limit": limit,
            "offset": offset,
            "has_more": result.get("has_more", False),
            "include_descendants": include_descendants,
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="assign_fact_to_category",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/facts/{fact_id}/category")
async def assign_fact_to_category(
    fact_id: str = Path(..., description="Fact UUID"),
    request: AssignFactToCategoryRequest = ...,
    req: Request = None,
):
    """
    Assign a fact to a category.

    Issue #411: Category assignment to facts.

    Parameters:
    - fact_id: Fact UUID
    - category_id: Category UUID to assign to

    Returns:
    - status: success or error
    - fact_id: Assigned fact ID
    - category_id: Target category ID
    - category_path: Category path
    """
    # Validate fact_id format
    fact_id = fact_id.strip()
    if not _CATEGORY_ID_RE.match(fact_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid fact_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Assigning fact '%s' to category '%s'", fact_id, request.category_id)

    result = await kb.assign_fact_to_category(
        fact_id=fact_id,
        category_id=request.category_id,
    )

    if result.get("success"):
        return {
            "status": "success",
            "fact_id": result.get("fact_id"),
            "category_id": result.get("category_id"),
            "category_path": result.get("category_path"),
            "message": result.get("message", "Fact assigned to category"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_categories_by_path",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/categories/search")
async def search_categories_by_path(
    request: SearchCategoriesByPathRequest,
    req: Request = None,
):
    """
    Search categories by path pattern.

    Issue #411: Path-based queries.

    Parameters:
    - path_pattern: Path pattern with wildcards (e.g., "tech/python/*")
    - limit: Maximum results

    Returns:
    - status: success or error
    - categories: Matching categories
    - count: Number of matches
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.search_categories_by_path(
        path_pattern=request.path_pattern,
        limit=request.limit,
    )

    if result.get("success"):
        return {
            "status": "success",
            "pattern": result.get("pattern"),
            "categories": result.get("categories", []),
            "count": result.get("count", 0),
        }
    else:
        error_message = result.get("message", "Unknown error")
        raise HTTPException(status_code=500, detail=error_message)
