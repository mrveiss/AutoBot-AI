# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Relations API - Unified Graph + Vector Knowledge System

This API exposes the relation capabilities added to KnowledgeBase,
enabling a unified knowledge system that combines:
- Vector similarity search (ChromaDB)
- Graph-based relations between facts
- Hybrid search combining both

This eliminates the need for a separate AutoBotMemoryGraph system.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from knowledge_factory import get_or_create_knowledge_base
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for valid relation directions
_VALID_DIRECTIONS = frozenset({"outgoing", "incoming", "both"})

router = APIRouter(prefix="/relations", tags=["knowledge-relations"])


# ============================================================================
# Pydantic Models
# ============================================================================


class CreateRelationRequest(BaseModel):
    """Request model for creating a fact relation."""

    source_fact_id: str = Field(..., description="ID of the source fact")
    target_fact_id: str = Field(..., description="ID of the target fact")
    relation_type: str = Field(
        ...,
        description="Type of relation (e.g., relates_to, depends_on, implements)",
    )
    metadata: Optional[dict] = Field(
        None, description="Optional metadata for the relation"
    )


class DeleteRelationRequest(BaseModel):
    """Request model for deleting a fact relation."""

    source_fact_id: str = Field(..., description="ID of the source fact")
    target_fact_id: str = Field(..., description="ID of the target fact")
    relation_type: Optional[str] = Field(
        None, description="Specific relation type to delete (None = all relations)"
    )


class TraverseRequest(BaseModel):
    """Request model for graph traversal."""

    start_fact_id: str = Field(..., description="Starting fact ID for traversal")
    max_depth: int = Field(2, ge=1, le=5, description="Maximum traversal depth")
    relation_types: Optional[List[str]] = Field(
        None, description="Optional list of relation types to follow"
    )
    include_fact_details: bool = Field(
        False, description="Include full fact content in results"
    )


class HybridSearchRequest(BaseModel):
    """Request model for hybrid (vector + graph) search."""

    query: str = Field(..., description="Search query text")
    top_k: int = Field(10, ge=1, le=100, description="Number of vector matches")
    expand_relations: bool = Field(
        True, description="Expand results with graph relations"
    )
    relation_depth: int = Field(1, ge=1, le=3, description="Relation traversal depth")
    relation_types: Optional[List[str]] = Field(
        None, description="Filter by relation types"
    )


# ============================================================================
# API Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_fact_relation",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.post("/create")
async def create_fact_relation(req: Request, body: CreateRelationRequest):
    """
    Create a bidirectional relation between two facts.

    This enables graph-based knowledge retrieval alongside vector search.

    Valid relation types:
    - relates_to: General relationship
    - depends_on: Dependency relationship
    - implements: Implementation relationship
    - fixes: Bug fix relationship
    - informs: Information flow
    - guides: Guidance relationship
    - follows: Sequential relationship
    - contains: Containment relationship
    - blocks: Blocking relationship
    - references: Reference relationship
    - supersedes: Replacement relationship
    - contradicts: Contradiction relationship
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    result = await kb.create_fact_relation(
        source_fact_id=body.source_fact_id,
        target_fact_id=body.target_fact_id,
        relation_type=body.relation_type,
        metadata=body.metadata,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Failed to create relation"),
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_fact_relation",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.delete("/delete")
async def delete_fact_relation(req: Request, body: DeleteRelationRequest):
    """
    Delete a relation between two facts.

    If relation_type is not specified, deletes ALL relations between the facts.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    result = await kb.delete_fact_relation(
        source_fact_id=body.source_fact_id,
        target_fact_id=body.target_fact_id,
        relation_type=body.relation_type,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Failed to delete relation"),
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_relations",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.get("/fact/{fact_id}")
async def get_fact_relations(
    req: Request,
    fact_id: str,
    direction: str = Query(
        "both", description="Direction: 'outgoing', 'incoming', or 'both'"
    ),
    relation_type: Optional[str] = Query(None, description="Filter by relation type"),
    include_details: bool = Query(
        False, description="Include full fact content for related facts"
    ),
):
    """
    Get all relations for a specific fact.

    Returns incoming and/or outgoing relations based on the direction parameter.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    if direction not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail="Direction must be 'outgoing', 'incoming', or 'both'",
        )

    result = await kb.get_fact_relations(
        fact_id=fact_id,
        direction=direction,
        relation_type=relation_type,
        include_fact_details=include_details,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Failed to get relations"),
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="traverse_relations",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.post("/traverse")
async def traverse_relations(req: Request, body: TraverseRequest):
    """
    Traverse the fact graph starting from a given fact.

    Performs a breadth-first traversal of related facts up to max_depth.
    Returns all reachable nodes and edges.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    result = await kb.traverse_relations(
        start_fact_id=body.start_fact_id,
        max_depth=body.max_depth,
        relation_types=body.relation_types,
        include_fact_details=body.include_fact_details,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Failed to traverse relations"),
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="hybrid_search",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.post("/hybrid-search")
async def hybrid_search(req: Request, body: HybridSearchRequest):
    """
    Perform hybrid search combining vector similarity and graph relations.

    This unifies the previously separate RAG and Graph search capabilities:
    1. Vector search finds semantically similar facts
    2. Graph expansion retrieves related facts via relations

    Results include both vector matches and graph-expanded facts.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    result = await kb.hybrid_search(
        query=body.query,
        top_k=body.top_k,
        expand_relations=body.expand_relations,
        relation_depth=body.relation_depth,
        relation_types=body.relation_types,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Hybrid search failed"),
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_relation_stats",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.get("/stats")
async def get_relation_stats(req: Request):
    """
    Get statistics about fact relations in the knowledge base.

    Returns total relation count, relations by type, and available relation types.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    result = await kb.get_relation_stats()

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("message", "Failed to get relation stats"),
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_available_relation_types",
    error_code_prefix="KNOWLEDGE_REL",
)
@router.get("/types")
async def get_available_relation_types(req: Request):
    """
    Get list of valid relation types.

    Use this to discover what relation types are supported.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        # Return hardcoded types if KB not available
        return {
            "success": True,
            "relation_types": [
                {"name": "relates_to", "description": "General relationship"},
                {"name": "depends_on", "description": "Dependency relationship"},
                {"name": "implements", "description": "Implementation relationship"},
                {"name": "fixes", "description": "Bug fix relationship"},
                {"name": "informs", "description": "Information flow"},
                {"name": "guides", "description": "Guidance relationship"},
                {"name": "follows", "description": "Sequential relationship"},
                {"name": "contains", "description": "Containment relationship"},
                {"name": "blocks", "description": "Blocking relationship"},
                {"name": "references", "description": "Reference relationship"},
                {"name": "supersedes", "description": "Replacement relationship"},
                {"name": "contradicts", "description": "Contradiction relationship"},
            ],
        }

    return {
        "success": True,
        "relation_types": [
            {"name": rt, "description": f"{rt.replace('_', ' ').title()} relationship"}
            for rt in sorted(kb.RELATION_TYPES)
        ],
    }
