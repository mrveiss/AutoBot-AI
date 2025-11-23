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
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from src.autobot_memory_graph import AutoBotMemoryGraph
from src.constants.network_constants import NetworkConstants
from src.utils.error_boundaries import ErrorCategory, with_error_handling

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
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )
    tags: Optional[List[str]] = Field(
        default_factory=list, description="Classification tags"
    )

    @validator("entity_type")
    def validate_entity_type(cls, v):
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
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @validator("relation_type")
    def validate_relation_type(cls, v):
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
    metadata: Dict[str, Any]


class RelationResponse(BaseModel):
    """Response model for relation data"""

    to: str
    type: str
    created_at: int
    metadata: Dict[str, Any]


class GraphNodeResponse(BaseModel):
    """Response model for graph node with relations"""

    entity: EntityResponse
    relations: Dict[str, List[RelationResponse]]


class SearchResponse(BaseModel):
    """Response model for search results"""

    entities: List[EntityResponse]
    total_count: int
    query: str
    filters: Dict[str, Any]


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


def generate_request_id() -> str:
    """Generate unique request ID for tracking"""
    return str(uuid.uuid4())


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
    entity_data: EntityCreateRequest,
    request: Request,
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Create a new entity in the memory graph

    Args:
        entity_data: Entity creation request data
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

        logger.info(f"[{request_id}] Entity created successfully: {entity['id']}")

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
        logger.warning(f"[{request_id}] Validation error creating entity: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[{request_id}] Error creating entity: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create entity: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_entity_by_id",
    error_code_prefix="MEMORY",
)
@router.get("/entities/{entity_id}")
async def get_entity_by_id(
    entity_id: str = Path(..., description="Entity UUID"),
    include_relations: bool = Query(False, description="Include related entities"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entity by ID

    Args:
        entity_id: Entity UUID
        include_relations: Include related entities in response
        memory_graph: Memory graph instance

    Returns:
        Entity data with optional relations

    Raises:
        HTTPException: If entity not found
    """
    request_id = generate_request_id()

    try:
        logger.info(f"[{request_id}] Retrieving entity: {entity_id}")

        entity = await memory_graph.get_entity(
            entity_id=entity_id, include_relations=include_relations
        )

        if entity is None:
            logger.warning(f"[{request_id}] Entity not found: {entity_id}")
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        logger.info(f"[{request_id}] Entity retrieved: {entity['name']}")

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": entity, "request_id": request_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error retrieving entity: {e}")
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
    name: str = Query(..., description="Entity name to search for"),
    include_relations: bool = Query(False, description="Include related entities"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entity by name

    Args:
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
        logger.info(f"[{request_id}] Searching for entity by name: {name}")

        entity = await memory_graph.get_entity(
            entity_name=name, include_relations=include_relations
        )

        if entity is None:
            logger.warning(f"[{request_id}] Entity not found: {name}")
            raise HTTPException(status_code=404, detail=f"Entity not found: {name}")

        logger.info(f"[{request_id}] Entity found: {entity['id']}")

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": entity, "request_id": request_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error searching entity: {e}")
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
    observation_data: ObservationAddRequest = Body(...),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Add observations to an existing entity

    Args:
        entity_id: Entity UUID (used to find entity by name from ID)
        observation_data: Observations to add
        memory_graph: Memory graph instance

    Returns:
        Updated entity data

    Raises:
        HTTPException: If entity not found or update fails
    """
    request_id = generate_request_id()

    try:
        logger.info(f"[{request_id}] Adding observations to entity: {entity_id}")

        # First get the entity to retrieve its name
        entity = await memory_graph.get_entity(entity_id=entity_id)
        if entity is None:
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        entity_name = entity["name"]

        # Add observations using entity name
        updated_entity = await memory_graph.add_observations(
            entity_name=entity_name, observations=observation_data.observations
        )

        logger.info(
            f"[{request_id}] Added {len(observation_data.observations)} observations to {entity_name}"
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": updated_entity,
                "message": f"Added {len(observation_data.observations)} observations",
                "request_id": request_id,
            },
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"[{request_id}] Validation error adding observations: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[{request_id}] Error adding observations: {e}")
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
    cascade_relations: bool = Query(
        True, description="Delete all relations to/from this entity"
    ),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Delete entity and optionally its relations

    Args:
        entity_id: Entity UUID
        cascade_relations: Delete all relations
        memory_graph: Memory graph instance

    Returns:
        Deletion confirmation

    Raises:
        HTTPException: If entity not found or deletion fails
    """
    request_id = generate_request_id()

    try:
        logger.info(f"[{request_id}] Deleting entity: {entity_id}")

        # First get the entity to retrieve its name
        entity = await memory_graph.get_entity(entity_id=entity_id)
        if entity is None:
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        entity_name = entity["name"]

        # Delete using entity name
        deleted = await memory_graph.delete_entity(
            entity_name=entity_name, cascade_relations=cascade_relations
        )

        if not deleted:
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        logger.info(f"[{request_id}] Entity deleted: {entity_name}")

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error deleting entity: {e}")
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
    relation_data: RelationCreateRequest,
    request: Request,
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Create relationship between two entities

    Args:
        relation_data: Relation creation request data
        memory_graph: Memory graph instance

    Returns:
        Created relation data

    Raises:
        HTTPException: If relation creation fails
    """
    request_id = generate_request_id()

    try:
        logger.info(
            f"[{request_id}] Creating relation: {relation_data.from_entity} --[{relation_data.relation_type}]--> {relation_data.to_entity}"
        )

        relation = await memory_graph.create_relation(
            from_entity=relation_data.from_entity,
            to_entity=relation_data.to_entity,
            relation_type=relation_data.relation_type,
            bidirectional=relation_data.bidirectional,
            strength=relation_data.strength,
            metadata=relation_data.metadata,
        )

        logger.info(f"[{request_id}] Relation created successfully")

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
        logger.warning(f"[{request_id}] Validation error creating relation: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[{request_id}] Error creating relation: {e}")
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
    relation_type: Optional[str] = Query(None, description="Filter by relation type"),
    direction: str = Query(
        "both", regex="^(outgoing|incoming|both)$", description="Relation direction"
    ),
    max_depth: int = Query(
        1, ge=1, le=3, description="Relationship traversal depth (1-3)"
    ),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entities related to specified entity

    Args:
        entity_id: Entity UUID
        relation_type: Filter by relation type (optional)
        direction: Relation direction (outgoing, incoming, both)
        max_depth: Traversal depth
        memory_graph: Memory graph instance

    Returns:
        List of related entities with relation metadata

    Raises:
        HTTPException: If entity not found
    """
    request_id = generate_request_id()

    try:
        logger.info(f"[{request_id}] Getting related entities for: {entity_id}")

        # First get the entity to retrieve its name
        entity = await memory_graph.get_entity(entity_id=entity_id)
        if entity is None:
            raise HTTPException(
                status_code=404, detail=f"Entity not found: {entity_id}"
            )

        entity_name = entity["name"]

        # Get related entities
        related = await memory_graph.get_related_entities(
            entity_name=entity_name,
            relation_type=relation_type,
            direction=direction,
            max_depth=max_depth,
        )

        logger.info(f"[{request_id}] Found {len(related)} related entities")

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error getting related entities: {e}")
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
    from_entity: str = Query(..., description="Source entity name"),
    to_entity: str = Query(..., description="Target entity name"),
    relation_type: str = Query(..., description="Relation type to delete"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Delete specific relation between entities

    Args:
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
            f"[{request_id}] Deleting relation: {from_entity} --[{relation_type}]--> {to_entity}"
        )

        deleted = await memory_graph.delete_relation(
            from_entity=from_entity, to_entity=to_entity, relation_type=relation_type
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Relation not found: {from_entity} --[{relation_type}]--> {to_entity}",
            )

        logger.info(f"[{request_id}] Relation deleted successfully")

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error deleting relation: {e}")
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
    query: str = Query(..., min_length=1, description="Search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results to return"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Semantic search across all entities

    Args:
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
            f"[{request_id}] Searching entities: query='{query}', type={entity_type}, limit={limit}"
        )

        # Parse tags if provided
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        # Execute search
        entities = await memory_graph.search_entities(
            query=query,
            entity_type=entity_type,
            tags=tag_list,
            status=status,
            limit=limit,
        )

        logger.info(f"[{request_id}] Search returned {len(entities)} entities")

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
        logger.error(f"[{request_id}] Error searching entities: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_entity_graph",
    error_code_prefix="MEMORY",
)
@router.get("/graph")
async def get_entity_graph(
    entity_id: Optional[str] = Query(None, description="Root entity ID (optional)"),
    max_depth: int = Query(2, ge=1, le=3, description="Graph traversal depth"),
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Get entity graph with relations

    Args:
        entity_id: Root entity ID (if None, returns full graph sample)
        max_depth: Traversal depth
        memory_graph: Memory graph instance

    Returns:
        Entity graph structure with nodes and edges
    """
    request_id = generate_request_id()

    try:
        logger.info(
            f"[{request_id}] Building entity graph: root={entity_id}, depth={max_depth}"
        )

        if entity_id:
            # Get specific entity's graph
            entity = await memory_graph.get_entity(
                entity_id=entity_id, include_relations=True
            )

            if entity is None:
                raise HTTPException(
                    status_code=404, detail=f"Entity not found: {entity_id}"
                )

            graph_data = {"root_entity": entity, "max_depth": max_depth}
        else:
            # Return sample of recent entities
            entities = await memory_graph.search_entities(query="*", limit=50)

            graph_data = {
                "entities": entities[:20],  # Limit to 20 for graph visualization
                "total_available": len(entities),
                "note": (
                    "Showing sample of entities. Provide entity_id for specific graph."
                ),
            }

        logger.info(f"[{request_id}] Graph data prepared")

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": graph_data, "request_id": request_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Error building graph: {e}")
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
    memory_graph: AutoBotMemoryGraph = Depends(get_memory_graph),
) -> JSONResponse:
    """
    Health check for Memory Graph service

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
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
