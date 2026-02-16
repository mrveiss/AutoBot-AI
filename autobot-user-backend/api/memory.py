# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Memory Graph REST API Endpoints

This module provides REST API endpoints for the AutoBot Memory Graph system,
enabling entity management, relationship tracking, and semantic search capabilities.

Key Features:
- Entity CRUD operations (Create, Read, Update, Delete)
- Relationship management between entities
- Semantic search across entities
- Graph traversal and visualization
- Integration with existing AutoBot backend patterns

Architecture:
- FastAPI router with async/await patterns
- Pydantic models for validation
- Dependency injection for AutoBotMemoryGraph
- Consistent error handling and logging
- RESTful endpoint design

Performance:
- Entity operations: <50ms
- Search queries: <200ms
- Relation traversal: <100ms
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from auth_middleware import check_admin_permission
from autobot_memory_graph import AutoBotMemoryGraph
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.type_defs.common import Metadata
from backend.utils.request_utils import generate_request_id

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["memory"])
logger = logging.getLogger(__name__)

# ====================================================================
# Request/Response Models
# ====================================================================


class EntityCreateRequest(BaseModel):
    """Request model for creating a new entity"""

    entity_type: str = Field(
        ..., description="Type of entity (conversation, bug_fix, feature, etc.)"
    )
    name: str = Field(
        ..., min_length=1, max_length=200, description="Human-readable entity name"
    )
    observations: List[str] = Field(
        ..., min_items=1, description="List of observation strings"
    )
    metadata: Optional[Metadata] = Field(
        default_factory=dict, description="Additional metadata"
    )
    tags: Optional[List[str]] = Field(
        default_factory=list, description="Classification tags"
    )

    @validator("entity_type")
    def validate_entity_type(cls, v):
        """Validate entity type against allowed values."""
        valid_types = {
            "conversation",
            "bug_fix",
            "feature",
            "decision",
            "task",
            "user_preference",
            "context",
            "learning",
            "research",
            "implementation",
        }
        if v not in valid_types:
            raise ValueError(f"entity_type must be one of: {valid_types}")
        return v


class ObservationAddRequest(BaseModel):
    """Request model for adding observations to an entity"""

    observations: List[str] = Field(
        ..., min_items=1, description="New observations to add"
    )


class RelationCreateRequest(BaseModel):
    """Request model for creating a relationship between entities"""

    from_entity: str = Field(..., description="Source entity name")
    to_entity: str = Field(..., description="Target entity name")
    relation_type: str = Field(..., description="Type of relationship")
    bidirectional: bool = Field(
        default=False, description="Create reverse relation as well"
    )
    strength: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Relationship strength (0.0-1.0)"
    )
    metadata: Optional[Metadata] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @validator("relation_type")
    def validate_relation_type(cls, v):
        """Validate relation type against allowed values."""
        valid_types = {
            "relates_to",
            "depends_on",
            "implements",
            "fixes",
            "informs",
            "guides",
            "follows",
            "contains",
            "blocks",
        }
        if v not in valid_types:
            raise ValueError(f"relation_type must be one of: {valid_types}")
        return v


class EntityResponse(BaseModel):
    """Response model for entity data"""

    id: str
    type: str
    name: str
    created_at: int
    updated_at: int
    observations: List[str]
    metadata: Metadata


class RelationResponse(BaseModel):
    """Response model for relation data"""

    to: str
    type: str
    created_at: int
    metadata: Metadata


class GraphNodeResponse(BaseModel):
    """Response model for graph node with relations"""

    entity: EntityResponse
    relations: Dict[str, List[RelationResponse]]


class SearchResponse(BaseModel):
    """Response model for search results"""

    entities: List[EntityResponse]
    total_count: int
    query: str
    filters: Metadata


# ====================================================================
# Dependency Injection
# ====================================================================


def get_memory_graph(request: Request) -> AutoBotMemoryGraph:
    """
    Get Memory Graph instance from app state with lazy initialization

    Args:
        request: FastAPI request object

    Returns:
        AutoBotMemoryGraph: Initialized memory graph instance

    Raises:
        HTTPException: If memory graph is not available
    """
    memory_graph = getattr(request.app.state, "memory_graph", None)

    if memory_graph is None:
        logger.error("Memory Graph not initialized in app state")
        raise HTTPException(
            status_code=503, detail="Memory Graph service not available"
        )

    if not memory_graph.initialized:
        logger.error("Memory Graph not properly initialized")
        raise HTTPException(status_code=503, detail="Memory Graph not initialized")

    return memory_graph


# ====================================================================
# Helper Functions (Issue #398: Extracted to reduce method length)
# ====================================================================


async def _get_entity_name_by_id(
    memory_graph: AutoBotMemoryGraph, entity_id: str
) -> str:
    """
    Get entity name from ID. Issue #398: Extracted common pattern.

    Args:
        memory_graph: Memory graph instance
        entity_id: Entity UUID

    Returns:
        Entity name

    Raises:
        HTTPException: If entity not found
    """
    entity = await memory_graph.get_entity(entity_id=entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    return entity["name"]


def _parse_tag_list(tags: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated tags into list. Issue #398: Extracted."""
    if not tags:
        return None
    return [tag.strip() for tag in tags.split(",") if tag.strip()]


def _build_delete_entity_response(
    request_id: str,
    entity_id: str,
    entity_name: str,
    cascade_relations: bool,
) -> JSONResponse:
    """
    Build success response for entity deletion.

    Issue #620: Extracted from delete_entity to reduce function length.

    Args:
        request_id: Request tracking ID
        entity_id: Deleted entity UUID
        entity_name: Deleted entity name
        cascade_relations: Whether relations were cascaded

    Returns:
        JSONResponse with deletion confirmation
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "deleted": True,
                "cascade_relations": cascade_relations,
            },
            "message": "Entity deleted successfully",
            "request_id": request_id,
        },
    )


def _build_delete_relation_response(
    request_id: str,
    from_entity: str,
    to_entity: str,
    relation_type: str,
) -> JSONResponse:
    """
    Build success response for relation deletion.

    Issue #620: Extracted from delete_relation to reduce function length.

    Args:
        request_id: Request tracking ID
        from_entity: Source entity name
        to_entity: Target entity name
        relation_type: Type of deleted relation

    Returns:
        JSONResponse with deletion confirmation
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "from_entity": from_entity,
                "to_entity": to_entity,
                "relation_type": relation_type,
                "deleted": True,
            },
            "message": "Relation deleted successfully",
            "request_id": request_id,
        },
    )


async def _get_entity_graph_for_id(
    memory_graph: AutoBotMemoryGraph,
    entity_id: str,
    max_depth: int,
) -> Dict:
    """
    Get graph data for a specific entity.

    Issue #620: Extracted from get_entity_graph to reduce function length.

    Args:
        memory_graph: Memory graph instance
        entity_id: Root entity UUID
        max_depth: Graph traversal depth

    Returns:
        Dict with entity graph data

    Raises:
        HTTPException: If entity not found
    """
    entity = await memory_graph.get_entity(entity_id=entity_id, include_relations=True)

    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")

    return {"root_entity": entity, "max_depth": max_depth}


async def _get_entity_graph_sample(memory_graph: AutoBotMemoryGraph) -> Dict:
    """
    Get a sample of entities for graph visualization.

    Issue #620: Extracted from get_entity_graph to reduce function length.

    Args:
        memory_graph: Memory graph instance

    Returns:
        Dict with sample entity graph data
    """
    entities = await memory_graph.search_entities(query="*", limit=50)

    return {
        "entities": entities[:20],  # Limit to 20 for graph visualization
        "total_available": len(entities),
        "note": "Showing sample of entities. Provide entity_id for specific graph.",
    }


def _build_related_entities_response(
    request_id: str,
    entity_id: str,
    entity_name: str,
    related: List[Dict],
    relation_type: Optional[str],
    direction: str,
    max_depth: int,
) -> JSONResponse:
    """
    Build response for get_related_entities operation.

    Issue #620: Extracted from get_related_entities.

    Args:
        request_id: Request tracking ID
        entity_id: Source entity UUID
        entity_name: Source entity name
        related: List of related entities
        relation_type: Filter applied (if any)
        direction: Direction filter
        max_depth: Traversal depth used

    Returns:
        JSONResponse with related entities data
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "entity_id": entity_id,
                "entity_name": entity_name,
                "related_entities": related,
                "total_count": len(related),
                "filters": {
                    "relation_type": relation_type,
                    "direction": direction,
                    "max_depth": max_depth,
                },
            },
            "request_id": request_id,
        },
    )


def _build_list_entities_response(
    request_id: str,
    entities: List[Dict],
    entity_type: Optional[str],
    limit: int,
) -> JSONResponse:
    """
    Build response for list_all_entities operation.

    Issue #620: Extracted from list_all_entities.

    Args:
        request_id: Request tracking ID
        entities: List of entities found
        entity_type: Type filter applied (if any)
        limit: Limit applied

    Returns:
        JSONResponse with entities list
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "entities": entities,
                "total_count": len(entities),
                "filters": {
                    "entity_type": entity_type,
                    "limit": limit,
                },
            },
            "request_id": request_id,
        },
    )


# ====================================================================
# Entity Management Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_entity",
    error_code_prefix="MEMORY",
)
@router.post("/entities", status_code=201)
async def create_entity(
    admin_check: bool = Depends(check_admin_permission),
    entity_data: EntityCreateRequest = Body(...),
    request: Request = None,
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Create a new entity in the memory graph

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        entity_data: Entity creation request data
        request: FastAPI request object
        memory_graph: Memory graph instance

    Returns:
        Created entity with metadata

    Raises:
        HTTPException: If entity creation fails
    """
    request_id = generate_request_id()

    try:
        logger.info(
            f"[{request_id}] Creating entity: {entity_data.name} ({entity_data.entity_type})"
        )

        entity = await memory_graph.create_entity(
            entity_type=entity_data.entity_type,
            name=entity_data.name,
            observations=entity_data.observations,
            metadata=entity_data.metadata,
            tags=entity_data.tags,
        )

        logger.info("[%s] Entity created successfully: %s", request_id, entity["id"])

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "data": entity,
                "message": "Entity created successfully",
                "request_id": request_id,
            },
        )

    except ValueError as e:
        logger.warning("[%s] Validation error creating entity: %s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[%s] Error creating entity: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to create entity: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_all_entities",
    error_code_prefix="MEMORY",
)
@router.get("/entities/all")
async def list_all_entities(
    admin_check: bool = Depends(check_admin_permission),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results to return"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    List all entities in the memory graph.

    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.

    Note: Must be defined BEFORE /entities/{entity_id} for proper routing.
    """
    request_id = generate_request_id()

    try:
        logger.info(
            "[%s] Listing entities: type=%s, limit=%s", request_id, entity_type, limit
        )

        entities = await memory_graph.search_entities(
            query="*", entity_type=entity_type, limit=limit
        )

        logger.info("[%s] Found %s entities", request_id, len(entities))
        return _build_list_entities_response(request_id, entities, entity_type, limit)

    except Exception as e:
        logger.error("[%s] Error listing entities: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to list entities: {str(e)}"
        )


# ====================================================================
# Orphan Cleanup Endpoints (Issue #547)
# IMPORTANT: Must be defined BEFORE /entities/{entity_id} for proper routing
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_orphaned_conversation_entities",
    error_code_prefix="MEMORY",
)
@router.get("/entities/orphans")
async def find_orphaned_conversation_entities(
    admin_check: bool = Depends(check_admin_permission),
    request: Request = None,
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Find conversation entities that reference deleted sessions.

    Issue #547: Detects memory entities of type 'conversation' that have
    session_id metadata pointing to sessions that no longer exist.
    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Scanning for orphaned conversation entities", request_id)

        all_entities = await memory_graph.search_entities(
            query="*", entity_type="conversation", limit=1000
        )

        if not all_entities:
            return _build_empty_orphan_response(
                request_id, "No conversation entities found"
            )

        existing_session_ids = await _get_existing_session_ids(request)
        orphaned_raw = _find_orphaned_entities(all_entities, existing_session_ids)
        orphaned_entities = _format_orphaned_for_response(orphaned_raw)

        logger.info(
            "[%s] Found %d orphaned of %d entities",
            request_id,
            len(orphaned_entities),
            len(all_entities),
        )

        return _build_orphan_scan_response(
            request_id, all_entities, existing_session_ids, orphaned_entities
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error finding orphaned entities: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to find orphaned entities: {str(e)}"
        )


# =============================================================================
# Orphan Cleanup Helpers (Issue #547)
# =============================================================================


async def _get_existing_session_ids(request: Request) -> set:
    """
    Get set of existing session IDs from chat manager.

    Args:
        request: FastAPI request for dependency access

    Returns:
        Set of existing session IDs

    Raises:
        HTTPException: If chat manager unavailable
    """
    from backend.utils.chat_utils import get_chat_history_manager

    chat_manager = get_chat_history_manager(request)
    if chat_manager is None:
        raise HTTPException(
            status_code=500, detail="Chat history manager not available"
        )

    existing_sessions = await chat_manager.list_sessions_fast()
    return {s["id"] for s in existing_sessions}


def _find_orphaned_entities(
    entities: List[Dict], existing_session_ids: set
) -> List[Dict]:
    """
    Find entities that reference non-existent sessions.

    Args:
        entities: All conversation entities
        existing_session_ids: Set of valid session IDs

    Returns:
        List of orphaned entities
    """
    orphaned = []
    for entity in entities:
        metadata = entity.get("metadata", {})
        session_id = metadata.get("session_id")

        if session_id and session_id not in existing_session_ids:
            orphaned.append(entity)

    return orphaned


def _format_orphaned_for_response(orphaned_entities: List[Dict]) -> List[Dict]:
    """
    Format orphaned entities for API response.

    Issue #665: Extracted helper for response formatting.

    Args:
        orphaned_entities: Raw orphaned entities

    Returns:
        List of formatted entity dicts for response
    """
    return [
        {
            "id": entity.get("id"),
            "name": entity.get("name"),
            "session_id": entity.get("metadata", {}).get("session_id"),
            "created_at": entity.get("created_at"),
            "observations": entity.get("observations", [])[:3],  # First 3
        }
        for entity in orphaned_entities
    ]


def _build_orphan_scan_response(
    request_id: str,
    all_entities: List[Dict],
    existing_session_ids: set,
    orphaned_entities: List[Dict],
) -> JSONResponse:
    """
    Build response for orphan scan operation.

    Issue #620: Extracted from find_orphaned_conversation_entities.

    Args:
        request_id: Request tracking ID
        all_entities: All conversation entities found
        existing_session_ids: Set of valid session IDs
        orphaned_entities: Formatted orphaned entities

    Returns:
        JSONResponse with scan results
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "total_conversation_entities": len(all_entities),
                "active_sessions": len(existing_session_ids),
                "orphaned_count": len(orphaned_entities),
                "orphaned_entities": orphaned_entities,
            },
            "request_id": request_id,
        },
    )


def _build_empty_orphan_response(request_id: str, message: str) -> JSONResponse:
    """
    Build response when no conversation entities found.

    Issue #620: Extracted from find_orphaned_conversation_entities.

    Args:
        request_id: Request tracking ID
        message: Response message

    Returns:
        JSONResponse with empty results
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "total_conversation_entities": 0,
                "orphaned_count": 0,
                "orphaned_entities": [],
            },
            "message": message,
            "request_id": request_id,
        },
    )


async def _delete_entities(
    memory_graph: AutoBotMemoryGraph,
    entities: List[Dict],
    request_id: str,
) -> tuple:
    """
    Delete a list of entities from memory graph.

    Args:
        memory_graph: Memory graph instance
        entities: Entities to delete
        request_id: Request ID for logging

    Returns:
        Tuple of (deleted_count, failed_deletions list)
    """
    deleted_count = 0
    failed_deletions = []

    logger.info(
        "[%s] Deleting %d orphaned conversation entities", request_id, len(entities)
    )

    for entity in entities:
        entity_name = entity.get("name")
        try:
            deleted = await memory_graph.delete_entity(
                entity_name=entity_name, cascade_relations=True
            )
            if deleted:
                deleted_count += 1
            else:
                failed_deletions.append(
                    {
                        "id": entity.get("id"),
                        "name": entity_name,
                        "reason": "delete returned False",
                    }
                )
        except Exception as e:
            logger.warning(
                "[%s] Failed to delete entity %s: %s", request_id, entity_name, e
            )
            failed_deletions.append(
                {"id": entity.get("id"), "name": entity_name, "reason": str(e)}
            )

    logger.info(
        "[%s] Deleted %d/%d orphaned entities", request_id, deleted_count, len(entities)
    )

    return deleted_count, failed_deletions


def _build_orphan_cleanup_response(
    request_id: str,
    dry_run: bool,
    orphaned_count: int,
    deleted_count: int = 0,
    failed_deletions: List[Dict] = None,
    message: str = None,
) -> JSONResponse:
    """
    Build response for orphan cleanup operation.

    Issue #620: Extracted from cleanup_orphaned_conversation_entities.
    """
    if message is None:
        message = (
            f"Would delete {orphaned_count} orphaned entities"
            if dry_run
            else f"Deleted {deleted_count} orphaned entities"
        )

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "data": {
                "dry_run": dry_run,
                "orphaned_count": orphaned_count,
                "deleted_count": deleted_count,
                "failed_count": len(failed_deletions) if failed_deletions else 0,
                "failed_deletions": failed_deletions[:10] if failed_deletions else None,
            },
            "message": message,
            "request_id": request_id,
        },
    )


async def _detect_orphaned_entities(
    memory_graph: AutoBotMemoryGraph, request: Request
) -> List[Dict]:
    """
    Detect orphaned conversation entities that reference deleted sessions.

    Issue #620: Extracted from cleanup_orphaned_conversation_entities.

    Args:
        memory_graph: Memory graph instance
        request: FastAPI request for accessing chat manager

    Returns:
        List of orphaned entities, empty list if none found
    """
    all_entities = await memory_graph.search_entities(
        query="*", entity_type="conversation", limit=1000
    )

    if not all_entities:
        return []

    existing_session_ids = await _get_existing_session_ids(request)
    return _find_orphaned_entities(all_entities, existing_session_ids)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_orphaned_conversation_entities",
    error_code_prefix="MEMORY",
)
@router.delete("/entities/orphans")
async def cleanup_orphaned_conversation_entities(
    admin_check: bool = Depends(check_admin_permission),
    request: Request = None,
    dry_run: bool = Query(True, description="If True, only report without deleting"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Delete conversation entities that reference deleted sessions.

    Issue #547: Cleans up orphaned memory entities from deleted conversations.
    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Cleanup orphans (dry_run=%s)", request_id, dry_run)

        orphaned_entities = await _detect_orphaned_entities(memory_graph, request)

        if not orphaned_entities:
            return _build_orphan_cleanup_response(
                request_id, dry_run, 0, message="No orphaned entities found"
            )

        deleted_count, failed_deletions = 0, []
        if not dry_run:
            deleted_count, failed_deletions = await _delete_entities(
                memory_graph, orphaned_entities, request_id
            )

        return _build_orphan_cleanup_response(
            request_id, dry_run, len(orphaned_entities), deleted_count, failed_deletions
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error cleaning up orphaned entities: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to cleanup orphaned entities: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_entity_by_id",
    error_code_prefix="MEMORY",
)
@router.get("/entities/{entity_id}")
async def get_entity_by_id(
    entity_id: str = Path(..., description="Entity UUID"),
    admin_check: bool = Depends(check_admin_permission),
    include_relations: bool = Query(False, description="Include related entities"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entity by ID

    Issue #744: Requires admin authentication.

    Args:
        entity_id: Entity UUID
        admin_check: Admin permission verification
        include_relations: Include related entities in response
        memory_graph: Memory graph instance

    Returns:
        Entity data with optional relations

    Raises:
        HTTPException: If entity not found
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Retrieving entity: %s", request_id, entity_id)

        entity = await memory_graph.get_entity(
            entity_id=entity_id, include_relations=include_relations
        )

        if entity is None:
            logger.warning("[%s] Entity not found: %s", request_id, entity_id)
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        logger.info("[%s] Entity retrieved: %s", request_id, entity["name"])

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": entity, "request_id": request_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error retrieving entity: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve entity: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_entity_by_name",
    error_code_prefix="MEMORY",
)
@router.get("/entities")
async def get_entity_by_name(
    admin_check: bool = Depends(check_admin_permission),
    name: str = Query(..., description="Entity name to search for"),
    include_relations: bool = Query(False, description="Include related entities"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entity by name

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        name: Entity name
        include_relations: Include related entities in response
        memory_graph: Memory graph instance

    Returns:
        Entity data with optional relations

    Raises:
        HTTPException: If entity not found
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Searching for entity by name: %s", request_id, name)

        entity = await memory_graph.get_entity(
            entity_name=name, include_relations=include_relations
        )

        if entity is None:
            logger.warning("[%s] Entity not found: %s", request_id, name)
            raise HTTPException(status_code=404, detail=f"Entity not found: {name}")

        logger.info("[%s] Entity found: %s", request_id, entity["id"])

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": entity, "request_id": request_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error searching entity: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to search entity: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_observations",
    error_code_prefix="MEMORY",
)
@router.patch("/entities/{entity_id}/observations")
async def add_observations(
    entity_id: str = Path(..., description="Entity UUID"),
    admin_check: bool = Depends(check_admin_permission),
    observation_data: ObservationAddRequest = Body(...),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Add observations to an existing entity

    Issue #744: Requires admin authentication.

    Args:
        entity_id: Entity UUID (used to find entity by name from ID)
        admin_check: Admin permission verification
        observation_data: Observations to add
        memory_graph: Memory graph instance

    Returns:
        Updated entity data

    Raises:
        HTTPException: If entity not found or update fails
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Adding observations to entity: %s", request_id, entity_id)
        entity_name = await _get_entity_name_by_id(memory_graph, entity_id)

        updated_entity = await memory_graph.add_observations(
            entity_name=entity_name, observations=observation_data.observations
        )
        obs_count = len(observation_data.observations)
        logger.info(
            "[%s] Added %s observations to %s", request_id, obs_count, entity_name
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": updated_entity,
                "message": f"Added {obs_count} observations",
                "request_id": request_id,
            },
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("[%s] Validation error adding observations: %s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[%s] Error adding observations: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to add observations: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_entity",
    error_code_prefix="MEMORY",
)
@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: str = Path(..., description="Entity UUID"),
    admin_check: bool = Depends(check_admin_permission),
    cascade_relations: bool = Query(
        True, description="Delete all relations to/from this entity"
    ),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Delete entity and optionally its relations.

    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.

    Args:
        entity_id: Entity UUID
        admin_check: Admin permission verification
        cascade_relations: Delete all relations
        memory_graph: Memory graph instance

    Returns:
        Deletion confirmation

    Raises:
        HTTPException: If entity not found or deletion fails
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Deleting entity: %s", request_id, entity_id)
        entity_name = await _get_entity_name_by_id(memory_graph, entity_id)

        deleted = await memory_graph.delete_entity(
            entity_name=entity_name, cascade_relations=cascade_relations
        )
        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        logger.info("[%s] Entity deleted: %s", request_id, entity_name)
        return _build_delete_entity_response(
            request_id, entity_id, entity_name, cascade_relations
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error deleting entity: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete entity: {str(e)}"
        )


# ====================================================================
# Relationship Management Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_relation",
    error_code_prefix="MEMORY",
)
@router.post("/relations", status_code=201)
async def create_relation(
    admin_check: bool = Depends(check_admin_permission),
    relation_data: RelationCreateRequest = Body(...),
    request: Request = None,
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Create relationship between two entities

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        relation_data: Relation creation request data
        request: FastAPI request object
        memory_graph: Memory graph instance

    Returns:
        Created relation data

    Raises:
        HTTPException: If relation creation fails
    """
    request_id = generate_request_id()

    try:
        logger.info(
            "[%s] Creating relation: %s --[%s]--> %s",
            request_id,
            relation_data.from_entity,
            relation_data.relation_type,
            relation_data.to_entity,
        )

        relation = await memory_graph.create_relation(
            from_entity=relation_data.from_entity,
            to_entity=relation_data.to_entity,
            relation_type=relation_data.relation_type,
            bidirectional=relation_data.bidirectional,
            strength=relation_data.strength,
            metadata=relation_data.metadata,
        )

        logger.info("[%s] Relation created successfully", request_id)

        return JSONResponse(
            status_code=201,
            content={
                "success": True,
                "data": relation,
                "message": "Relation created successfully",
                "request_id": request_id,
            },
        )

    except ValueError as e:
        logger.warning("[%s] Validation error creating relation: %s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[%s] Error creating relation: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to create relation: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_related_entities",
    error_code_prefix="MEMORY",
)
@router.get("/entities/{entity_id}/relations")
async def get_related_entities(
    entity_id: str = Path(..., description="Entity UUID"),
    admin_check: bool = Depends(check_admin_permission),
    relation_type: Optional[str] = Query(None, description="Filter by relation type"),
    direction: str = Query(
        "both", pattern="^(outgoing|incoming|both)$", description="Relation direction"
    ),
    max_depth: int = Query(
        1, ge=1, le=3, description="Relationship traversal depth (1-3)"
    ),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entities related to specified entity.

    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.
    """
    request_id = generate_request_id()

    try:
        logger.info("[%s] Getting related entities for: %s", request_id, entity_id)
        entity_name = await _get_entity_name_by_id(memory_graph, entity_id)

        related = await memory_graph.get_related_entities(
            entity_name=entity_name,
            relation_type=relation_type,
            direction=direction,
            max_depth=max_depth,
        )
        logger.info("[%s] Found %s related entities", request_id, len(related))

        return _build_related_entities_response(
            request_id,
            entity_id,
            entity_name,
            related,
            relation_type,
            direction,
            max_depth,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error getting related entities: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get related entities: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_relation",
    error_code_prefix="MEMORY",
)
@router.delete("/relations")
async def delete_relation(
    admin_check: bool = Depends(check_admin_permission),
    from_entity: str = Query(..., description="Source entity name"),
    to_entity: str = Query(..., description="Target entity name"),
    relation_type: str = Query(..., description="Relation type to delete"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Delete specific relation between entities.

    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        from_entity: Source entity name
        to_entity: Target entity name
        relation_type: Relation type
        memory_graph: Memory graph instance

    Returns:
        Deletion confirmation

    Raises:
        HTTPException: If relation not found or deletion fails
    """
    request_id = generate_request_id()

    try:
        logger.info(
            "[%s] Deleting relation: %s --[%s]--> %s",
            request_id,
            from_entity,
            relation_type,
            to_entity,
        )

        deleted = await memory_graph.delete_relation(
            from_entity=from_entity, to_entity=to_entity, relation_type=relation_type
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Relation not found: {from_entity} --[{relation_type}]--> {to_entity}",
            )

        logger.info("[%s] Relation deleted successfully", request_id)
        return _build_delete_relation_response(
            request_id, from_entity, to_entity, relation_type
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error deleting relation: %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"Failed to delete relation: {str(e)}"
        )


# ====================================================================
# Search Endpoints
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_entities",
    error_code_prefix="MEMORY",
)
@router.get("/search")
async def search_entities(
    admin_check: bool = Depends(check_admin_permission),
    query: str = Query(..., min_length=1, description="Search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Semantic search across all entities

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        query: Search query (full-text search)
        entity_type: Filter by entity type (optional)
        tags: Filter by tags (comma-separated, optional)
        status: Filter by status (optional)
        limit: Maximum results
        memory_graph: Memory graph instance

    Returns:
        List of matching entities sorted by relevance
    """
    request_id = generate_request_id()

    try:
        logger.info(
            f"[{request_id}] Searching: query='{query}', type={entity_type}, limit={limit}"
        )
        tag_list = _parse_tag_list(tags)

        entities = await memory_graph.search_entities(
            query=query,
            entity_type=entity_type,
            tags=tag_list,
            status=status,
            limit=limit,
        )
        logger.info("[%s] Search returned %s entities", request_id, len(entities))

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": {
                    "entities": entities,
                    "total_count": len(entities),
                    "query": query,
                    "filters": {
                        "entity_type": entity_type,
                        "tags": tag_list,
                        "status": status,
                        "limit": limit,
                    },
                },
                "request_id": request_id,
            },
        )

    except Exception as e:
        logger.error("[%s] Error searching entities: %s", request_id, e)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_entity_graph",
    error_code_prefix="MEMORY",
)
@router.get("/graph")
async def get_entity_graph(
    admin_check: bool = Depends(check_admin_permission),
    entity_id: Optional[str] = Query(None, description="Root entity ID (optional)"),
    max_depth: int = Query(2, ge=1, le=3, description="Graph traversal depth"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entity graph with relations.

    Issue #620: Refactored using Extract Method pattern.
    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        entity_id: Root entity ID (if None, returns full graph sample)
        max_depth: Traversal depth
        memory_graph: Memory graph instance

    Returns:
        Entity graph structure with nodes and edges
    """
    request_id = generate_request_id()

    try:
        logger.info(
            "[%s] Building entity graph: root=%s, depth=%s",
            request_id,
            entity_id,
            max_depth,
        )

        if entity_id:
            graph_data = await _get_entity_graph_for_id(
                memory_graph, entity_id, max_depth
            )
        else:
            graph_data = await _get_entity_graph_sample(memory_graph)

        logger.info("[%s] Graph data prepared", request_id)

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": graph_data, "request_id": request_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Error building graph: %s", request_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to build graph: {str(e)}")


# ====================================================================
# Health Check Endpoint
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="memory_health_check",
    error_code_prefix="MEMORY",
)
@router.get("/health")
async def memory_health_check(
    admin_check: bool = Depends(check_admin_permission),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Health check for Memory Graph service

    Issue #744: Requires admin authentication.

    Args:
        admin_check: Admin permission verification
        memory_graph: Memory graph instance

    Returns:
        Health status and component information
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "memory_graph": (
                    "healthy" if memory_graph.initialized else "unavailable"
                ),
                "redis_connection": (
                    "healthy" if memory_graph.redis_client else "unavailable"
                ),
                "knowledge_base": (
                    "healthy" if memory_graph.knowledge_base else "unavailable"
                ),
            },
        }

        overall_healthy = all(
            status == "healthy" for status in health_status["components"].values()
        )

        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(
            status_code=200 if overall_healthy else 503, content=health_status
        )

    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
