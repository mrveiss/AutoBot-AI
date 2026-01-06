# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Collection Management API - Collection operations (Issue #412).

This module contains all collection-related API endpoints for the knowledge base.

Endpoints:
- POST /collections - Create a new collection
- GET /collections - List all collections
- GET /collections/{collection_id} - Get single collection
- PUT /collections/{collection_id} - Update collection
- DELETE /collections/{collection_id} - Delete collection
- POST /collections/{collection_id}/facts - Add facts to collection
- DELETE /collections/{collection_id}/facts - Remove facts from collection
- GET /collections/{collection_id}/facts - List facts in collection
- POST /collections/{collection_id}/export - Export collection
- POST /collections/{collection_id}/bulk-delete - Bulk delete facts in collection
- GET /facts/{fact_id}/collections - Get collections for a fact

Related Issues: #77 (Organization), #412 (Collections)
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Path, Query
from src.constants.threshold_constants import QueryDefaults, Request

from backend.api.knowledge_models import (
    CollectionFactsRequest,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Issue #412: Pre-compiled regex for collection/fact ID validation
_COLLECTION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

# Create router for collection management endpoints
router = APIRouter(tags=["knowledge-collections"])


def _raise_kb_error(error_message: str, default_code: int = 500) -> None:
    """Raise appropriate HTTPException based on error message (#624)."""
    error_lower = error_message.lower()
    if "not found" in error_lower:
        raise HTTPException(status_code=404, detail=error_message)
    raise HTTPException(status_code=default_code, detail=error_message)


# ===== COLLECTION CRUD OPERATIONS (Issue #412) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/collections")
async def create_collection(
    request: CreateCollectionRequest,
    req: Request = None,
):
    """
    Create a new collection.

    Issue #412: Collections/Folders for grouping documents.

    Parameters:
    - name: Collection name
    - description: Optional description
    - icon: Optional icon identifier
    - color: Optional hex color code
    - metadata: Optional custom metadata

    Returns:
    - status: success or error
    - collection: Created collection data with ID
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Creating collection '%s'", request.name)

    result = await kb.create_collection(
        name=request.name,
        description=request.description,
        icon=request.icon,
        color=request.color,
        metadata=request.metadata,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection": result.get("collection"),
            "message": result.get("message", "Collection created successfully"),
        }
    else:
        error_message = result.get("message", "Unknown error")
        raise HTTPException(status_code=400, detail=error_message)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_collections",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/collections")
async def list_collections(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=QueryDefaults.DEFAULT_OFFSET, ge=0),
    sort_by: str = Query(default="name", regex="^(name|created_at|fact_count)$"),
    req: Request = None,
):
    """
    List all collections.

    Issue #412: Collections/Folders for grouping documents.

    Parameters:
    - limit: Maximum number of collections (default: 100)
    - offset: Pagination offset
    - sort_by: Sort field (name, created_at, fact_count)

    Returns:
    - status: success or error
    - collections: List of collections
    - total_count: Total number of collections
    """
    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.list_collections(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collections": result.get("collections", []),
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
    operation="get_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    req: Request = None,
):
    """
    Get a single collection by ID.

    Issue #412: Collections/Folders for grouping documents.

    Parameters:
    - collection_id: Collection UUID

    Returns:
    - status: success or error
    - collection: Collection data
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_collection(collection_id=collection_id)

    if result.get("success"):
        return {
            "status": "success",
            "collection": result.get("collection"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.put("/collections/{collection_id}")
async def update_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    request: UpdateCollectionRequest = ...,
    req: Request = None,
):
    """
    Update collection metadata.

    Issue #412: Collections/Folders for grouping documents.

    Parameters:
    - collection_id: Collection UUID
    - name: New name
    - description: New description
    - icon: New icon identifier
    - color: New hex color code
    - metadata: New custom metadata

    Returns:
    - status: success or error
    - collection: Updated collection data
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Updating collection '%s'", collection_id)

    result = await kb.update_collection(
        collection_id=collection_id,
        name=request.name,
        description=request.description,
        icon=request.icon,
        color=request.color,
        metadata=request.metadata,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection": result.get("collection"),
            "message": result.get("message", "Collection updated successfully"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    delete_facts: bool = Query(default=False, description="Also delete all facts"),
    req: Request = None,
):
    """
    Delete a collection.

    Issue #412: Collections/Folders for grouping documents.

    Parameters:
    - collection_id: Collection UUID to delete
    - delete_facts: If True, also delete all facts in collection

    Returns:
    - status: success or error
    - facts_in_collection: Number of facts in collection
    - facts_deleted: Number of facts deleted (if delete_facts=True)
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Deleting collection '%s' (delete_facts=%s)", collection_id, delete_facts)

    result = await kb.delete_collection(
        collection_id=collection_id,
        delete_facts=delete_facts,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection_id": result.get("collection_id"),
            "facts_in_collection": result.get("facts_in_collection", 0),
            "facts_deleted": result.get("facts_deleted", 0),
            "message": result.get("message", "Collection deleted successfully"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


# ===== COLLECTION MEMBERSHIP OPERATIONS (Issue #412) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_facts_to_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/collections/{collection_id}/facts")
async def add_facts_to_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    request: CollectionFactsRequest = ...,
    req: Request = None,
):
    """
    Add facts to a collection.

    Issue #412: Many-to-many relationship support.

    Parameters:
    - collection_id: Collection UUID
    - fact_ids: List of fact UUIDs to add

    Returns:
    - status: success or error
    - added_count: Number of facts added
    - already_in_collection: Number already present
    - not_found: List of fact IDs not found
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Adding %d facts to collection '%s'", len(request.fact_ids), collection_id)

    result = await kb.add_facts_to_collection(
        collection_id=collection_id,
        fact_ids=request.fact_ids,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection_id": result.get("collection_id"),
            "added_count": result.get("added_count", 0),
            "already_in_collection": result.get("already_in_collection", 0),
            "not_found": result.get("not_found", []),
            "total_facts": result.get("total_facts", 0),
            "message": result.get("message"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_facts_from_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/collections/{collection_id}/facts")
async def remove_facts_from_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    request: CollectionFactsRequest = ...,
    req: Request = None,
):
    """
    Remove facts from a collection.

    Issue #412: Many-to-many relationship support.

    Parameters:
    - collection_id: Collection UUID
    - fact_ids: List of fact UUIDs to remove

    Returns:
    - status: success or error
    - removed_count: Number of facts removed
    - not_in_collection: Number not in collection
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Removing %d facts from collection '%s'", len(request.fact_ids), collection_id)

    result = await kb.remove_facts_from_collection(
        collection_id=collection_id,
        fact_ids=request.fact_ids,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection_id": result.get("collection_id"),
            "removed_count": result.get("removed_count", 0),
            "not_in_collection": result.get("not_in_collection", 0),
            "total_facts": result.get("total_facts", 0),
            "message": result.get("message"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_in_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/collections/{collection_id}/facts")
async def get_facts_in_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=QueryDefaults.DEFAULT_OFFSET, ge=0),
    include_content: bool = Query(default=False, description="Include fact content"),
    req: Request = None,
):
    """
    Get all facts in a collection.

    Issue #412: Collections/Folders for grouping documents.

    Parameters:
    - collection_id: Collection UUID
    - limit: Maximum number of facts
    - offset: Pagination offset
    - include_content: Whether to include fact content

    Returns:
    - status: success or error
    - facts: List of facts
    - total_count: Total facts in collection
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.get_facts_in_collection(
        collection_id=collection_id,
        limit=limit,
        offset=offset,
        include_content=include_content,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection_id": result.get("collection_id"),
            "collection_name": result.get("collection_name"),
            "facts": result.get("facts", []),
            "total_count": result.get("total_count", 0),
            "returned_count": result.get("returned_count", 0),
            "limit": limit,
            "offset": offset,
            "has_more": result.get("has_more", False),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_collections",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/facts/{fact_id}/collections")
async def get_fact_collections(
    fact_id: str = Path(..., description="Fact UUID"),
    req: Request = None,
):
    """
    Get all collections a fact belongs to.

    Issue #412: Many-to-many relationship support.

    Parameters:
    - fact_id: Fact UUID

    Returns:
    - status: success or error
    - collections: List of collections
    - count: Number of collections
    """
    # Validate fact_id format
    fact_id = fact_id.strip()
    if not _COLLECTION_ID_RE.match(fact_id):
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

    result = await kb.get_fact_collections(fact_id=fact_id)

    if result.get("success"):
        return {
            "status": "success",
            "fact_id": result.get("fact_id"),
            "collections": result.get("collections", []),
            "count": result.get("count", 0),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


# ===== COLLECTION BULK OPERATIONS (Issue #412) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_collection",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/collections/{collection_id}/export")
async def export_collection(
    collection_id: str = Path(..., description="Collection UUID"),
    include_content: bool = Query(default=True, description="Include fact content"),
    include_metadata: bool = Query(default=True, description="Include fact metadata"),
    req: Request = None,
):
    """
    Export all facts in a collection.

    Issue #412: Collection-level bulk operations.

    Parameters:
    - collection_id: Collection UUID
    - include_content: Include fact content
    - include_metadata: Include fact metadata

    Returns:
    - status: success or error
    - collection: Collection info
    - facts: Exported facts
    - total_count: Number of facts
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    logger.info("Exporting collection '%s'", collection_id)

    result = await kb.export_collection(
        collection_id=collection_id,
        include_content=include_content,
        include_metadata=include_metadata,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection": result.get("collection"),
            "facts": result.get("facts", []),
            "total_count": result.get("total_count", 0),
            "exported_at": result.get("exported_at"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="bulk_delete_collection_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/collections/{collection_id}/bulk-delete")
async def bulk_delete_collection_facts(
    collection_id: str = Path(..., description="Collection UUID"),
    confirm: bool = Query(default=False, description="Must be True to delete"),
    req: Request = None,
):
    """
    Delete all facts in a collection.

    Issue #412: Collection-level bulk operations.

    Parameters:
    - collection_id: Collection UUID
    - confirm: Must be True to actually delete

    Returns:
    - status: success or error
    - deleted_count: Number of facts deleted
    """
    # Validate collection_id format
    collection_id = collection_id.strip()
    if not _COLLECTION_ID_RE.match(collection_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid collection_id format: only alphanumeric, hyphens, underscores",
        )

    # Get knowledge base instance
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized - please check logs for errors",
        )

    result = await kb.bulk_delete_collection_facts(
        collection_id=collection_id,
        confirm=confirm,
    )

    if result.get("success"):
        return {
            "status": "success",
            "collection_id": result.get("collection_id"),
            "facts_to_delete": result.get("facts_to_delete"),
            "deleted_count": result.get("deleted_count", 0),
            "confirm_required": result.get("confirm_required", False),
            "message": result.get("message"),
        }
    else:
        _raise_kb_error(result.get("message", "Unknown error"), 400)
