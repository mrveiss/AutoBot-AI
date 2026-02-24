# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Scope-Aware Knowledge Search API

Issue #679: Permission-filtered knowledge search that respects hierarchical access control.
"""

import logging
from typing import List, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request
from knowledge.search_filters import (
    augment_search_request_with_permissions,
    extract_user_context_from_request,
    filter_search_results_by_permission,
)
from knowledge_factory import get_or_create_knowledge_base
from pydantic import BaseModel, Field
from user_management.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/search", tags=["knowledge-search-scoped"])


# =============================================================================
# Pydantic Models
# =============================================================================


class ScopedSearchRequest(BaseModel):
    """Scoped search request with automatic permission filtering."""

    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum results")
    mode: str = Field(
        default="hybrid",
        pattern="^(semantic|keyword|hybrid|auto)$",
        description="Search mode",
    )
    category: Optional[str] = Field(default=None, description="Filter by category")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")
    min_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum score threshold"
    )
    enable_rag: bool = Field(default=False, description="Enable RAG enhancement")
    enable_reranking: bool = Field(default=False, description="Enable reranking")


# =============================================================================
# Endpoints - Scope-Aware Search
# =============================================================================


async def _resolve_search_context(request: Request, current_user: User, query: str):
    """Helper for scoped_search. Ref: #1088.

    Validates KB availability, extracts user context, and logs the search intent.
    Returns (kb, user_id, user_org_id, user_group_ids).
    Raises HTTPException(503) when the knowledge base is unavailable.
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    user_id, user_org_id, user_group_ids = extract_user_context_from_request(
        current_user
    )

    logger.info(
        "Scoped search for user %s (org: %s, groups: %d): %s",
        user_id,
        user_org_id,
        len(user_group_ids),
        query,
    )
    return kb, user_id, user_org_id, user_group_ids


async def _execute_permission_filtered_search(
    kb, search_request: ScopedSearchRequest, user_id, user_org_id, user_group_ids
):
    """Helper for scoped_search. Ref: #1088.

    Builds the ChromaDB permission filter, runs the search, and returns raw results.
    Raises HTTPException(500) when kb.search is unavailable.
    """
    permission_where = await augment_search_request_with_permissions(
        query=search_request.query,
        user_id=user_id,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
    )

    if not hasattr(kb, "search"):
        raise HTTPException(
            status_code=500, detail="Knowledge base search not available"
        )

    return await kb.search(
        query=search_request.query,
        top_k=search_request.top_k,
        filters=permission_where,
    )


async def _build_scoped_search_response(
    results,
    search_request: ScopedSearchRequest,
    user_id,
    user_org_id,
    user_group_ids,
    ownership_manager,
) -> dict:
    """Helper for scoped_search. Ref: #1088.

    Post-filters raw results by permission, logs outcome, and builds the response dict.
    """
    filtered_results = await filter_search_results_by_permission(
        results=results,
        user_id=user_id,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
        ownership_manager=ownership_manager,
    )

    logger.info(
        "Scoped search returned %d/%d accessible results",
        len(filtered_results),
        len(results),
    )

    return {
        "results": filtered_results,
        "total_results": len(filtered_results),
        "query": search_request.query,
        "mode": search_request.mode,
        "user_id": user_id,
        "filtered_by_permissions": True,
    }


@router.post("/scoped")
async def scoped_search(
    search_request: ScopedSearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Permission-aware knowledge search.

    Issue #679: Searches only knowledge accessible to the current user based on:
    - Ownership (user's own facts)
    - Visibility level (system/organization/group)
    - Group membership
    - Explicit sharing

    Args:
        search_request: Search parameters

    Returns:
        Filtered search results respecting user's access permissions
    """
    try:
        kb, user_id, user_org_id, user_group_ids = await _resolve_search_context(
            request, current_user, search_request.query
        )
        results = await _execute_permission_filtered_search(
            kb, search_request, user_id, user_org_id, user_group_ids
        )
        return await _build_scoped_search_response(
            results,
            search_request,
            user_id,
            user_org_id,
            user_group_ids,
            kb.ownership_manager,
        )

    except Exception as e:
        logger.error("Error in scoped search: %s", e)
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


async def _synthesize_rag_response(
    query: str,
    accessible_facts: list,
    user_id: str,
    scoped_results: dict,
) -> dict:
    """Helper for scoped_rag_search. Ref: #1088.

    Attempts RAG synthesis over the top-5 accessible facts.
    Falls back to returning the raw scoped results when the RAG agent
    is unavailable (ImportError).

    Args:
        query: Original search query string
        accessible_facts: Permission-filtered facts from scoped_search
        user_id: Authenticated user ID for response metadata
        scoped_results: Raw scoped_search response dict used as fallback

    Returns:
        RAG-synthesized response dict, or scoped_results with rag_enhanced=False
    """
    try:
        from agents.rag_agent import get_rag_agent

        rag_agent = get_rag_agent()
        context_texts = [
            f"{fact.get('title', 'Untitled')}: {fact.get('content', '')}"
            for fact in accessible_facts[:5]
        ]
        context = "\n\n".join(context_texts)
        rag_response = await rag_agent.generate_response(query=query, context=context)
        return {
            "query": query,
            "synthesized_response": rag_response.get("response", ""),
            "source_facts": accessible_facts[:5],
            "total_facts_used": len(accessible_facts[:5]),
            "user_id": user_id,
            "filtered_by_permissions": True,
            "rag_enhanced": True,
        }
    except ImportError:
        logger.warning("RAG agent not available, returning scoped results only")
        return {
            **scoped_results,
            "rag_enhanced": False,
            "message": "RAG agent not available",
        }


@router.post("/rag/scoped")
async def scoped_rag_search(
    search_request: ScopedSearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Permission-aware RAG-enhanced search.

    Issue #679: RAG search that only uses knowledge accessible to the user.
    Prevents information leakage through RAG synthesis.

    Args:
        search_request: Search parameters

    Returns:
        RAG-synthesized response using only accessible knowledge
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Extract user context (Issue #1088: context extracted here, synthesis delegated)
        user_id, user_org_id, user_group_ids = extract_user_context_from_request(
            current_user
        )

        logger.info(
            "Scoped RAG search for user %s: %s",
            user_id,
            search_request.query,
        )

        # Get accessible facts via permission-filtered search
        scoped_results = await scoped_search(
            search_request=search_request, request=request, current_user=current_user
        )
        accessible_facts = scoped_results["results"]

        # Synthesize RAG response (Issue #1088: uses helper)
        return await _synthesize_rag_response(
            query=search_request.query,
            accessible_facts=accessible_facts,
            user_id=user_id,
            scoped_results=scoped_results,
        )

    except Exception as e:
        logger.error("Error in scoped RAG search: %s", e)
        raise HTTPException(status_code=500, detail=f"RAG search failed: {e}")


@router.get("/accessible-scopes")
async def get_accessible_scopes(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get list of scopes user has access to.

    Issue #679: Returns visibility levels user can search within.

    Returns:
        List of accessible visibility scopes
    """
    try:
        # Extract user context
        user_id, user_org_id, user_group_ids = extract_user_context_from_request(
            current_user
        )

        # Build accessible scopes list
        scopes = [
            {"scope": "private", "description": "Your private knowledge"},
            {"scope": "shared", "description": "Knowledge shared with you"},
            {"scope": "system", "description": "System-wide knowledge"},
        ]

        if user_org_id:
            scopes.append(
                {
                    "scope": "organization",
                    "description": "Your organization's knowledge",
                }
            )

        if user_group_ids:
            scopes.append(
                {
                    "scope": "group",
                    "description": f"Knowledge from your {len(user_group_ids)} team(s)",
                }
            )

        return {
            "user_id": user_id,
            "organization_id": user_org_id,
            "group_count": len(user_group_ids),
            "accessible_scopes": scopes,
        }

    except Exception as e:
        logger.error("Error getting accessible scopes: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get scopes: {e}")
