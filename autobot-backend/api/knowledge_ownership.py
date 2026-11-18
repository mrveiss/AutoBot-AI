# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Ownership and Sharing API Endpoints

Handles user ownership, visibility, and sharing for knowledge base facts.

Issue #688: User ownership model for chat-derived knowledge
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from api.schemas_knowledge import (
    KnowledgeMyFactsResponse,
    KnowledgeSharedWithMeResponse,
    KnowledgeUpdateVisibilityResponse,
    UpdateVisibilityRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.api_routing.deprecated_redirects import add_deprecated_redirects
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.search_filters import can_read_fact, fact_not_found, object_metadata
from knowledge_factory import get_or_create_knowledge_base

logger = get_logger(__name__)

router = APIRouter(tags=["knowledge_ownership"])

# #18795: share/unshare live in ``knowledge_collaboration`` (owner or admin). The old
# paths, and their #18722 doubled-prefix forms, answer a one-hop 308 straight to it for
# one release; removal is tracked in #18793.
_COLLAB_SHARE = "/api/knowledge/collaboration/facts/{fact_id}/share"
_COLLAB_UNSHARE = _COLLAB_SHARE + "/{user_id_to_remove}?entity_type=user"
add_deprecated_redirects(
    router,
    {
        ("POST", "/facts/{fact_id}/share"): _COLLAB_SHARE,
        ("DELETE", "/facts/{fact_id}/share/{user_id_to_remove}"): _COLLAB_UNSHARE,
        ("POST", "/api/knowledge/facts/{fact_id}/share"): _COLLAB_SHARE,
        ("DELETE", "/api/knowledge/facts/{fact_id}/share/{user_id_to_remove}"): _COLLAB_UNSHARE,
    },
    absolute=True,
)
# #18722: the remaining doubled paths answer 308 for one release; removal tracked in #18793.
add_deprecated_redirects(
    router,
    {
        ("PUT", "/api/knowledge/facts/{fact_id}/visibility"): "/facts/{fact_id}/visibility",
        ("GET", "/api/knowledge/facts/mine"): "/facts/mine",
        ("GET", "/api/knowledge/facts/shared-with-me"): "/facts/shared-with-me",
    },
)


def _get_user_from_request(request: Request) -> str | None:
    """Extract user_id from JWT token in request.

    Args:
        request: FastAPI request object

    Returns:
        User ID from JWT or None if not authenticated
    """
    # Extract JWT payload from request state (set by auth middleware)
    user_payload = getattr(request.state, "user", None)
    if user_payload:
        return user_payload.get("user_id")
    return None


async def _get_fact_with_ownership(kb, fact_id: str, user_id: str):
    """Get fact and verify ownership access.

    Args:
        kb: Knowledge base instance
        fact_id: Fact ID to retrieve
        user_id: User ID requesting access

    Returns:
        Fact dict if accessible

    Raises:
        HTTPException: 404 if not found or not readable (#18220)
    """
    if not kb.ownership_manager:
        # #16662: without the ownership manager no access decision can be made -- deny.
        # Checked before the lookup so a degraded KB answers a missing and an existing fact alike (#18220).
        raise HTTPException(status_code=503, detail="Ownership management not available")

    fact = await asyncio.to_thread(kb.get_fact, fact_id)  # #16670: get_fact is synchronous
    if not fact:
        raise fact_not_found()

    metadata = fact["metadata"] = object_metadata(
        fact_id, fact.get("metadata")
    )  # #18220: normalised once for the route
    # #16662: every caller is behind check_admin_permission -- an explicit admin read (owner decision, #16654)
    has_access = await can_read_fact(kb.ownership_manager, fact_id, metadata, user_id=user_id, is_admin=True)

    if not has_access:
        raise fact_not_found()  # #18220: indistinguishable from a missing fact

    return fact


@router.put("/facts/{fact_id}/visibility", response_model=KnowledgeUpdateVisibilityResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_fact_visibility",
    error_code_prefix="KB_OWN",
)
async def update_fact_visibility(
    fact_id: str,
    request_body: UpdateVisibilityRequest,
    request: Request,
    _: dict = Depends(check_admin_permission),
):
    """Change fact visibility level (Issue #688).

    Args:
        fact_id: Fact ID to update
        request_body: Visibility update request
        request: FastAPI request
        _: Admin permission check (required)

    Returns:
        Success response with new visibility
    """
    user_id = _get_user_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    kb = await get_or_create_knowledge_base()

    # Get fact and verify ownership
    fact = await _get_fact_with_ownership(kb, fact_id, user_id)

    # Only owner can change visibility
    metadata = fact["metadata"]  # normalised once by _get_fact_with_ownership (#18220)
    owner_id = metadata.get("owner_id")
    if owner_id and owner_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the owner can change visibility",
        )

    # Update visibility in metadata
    metadata["visibility"] = request_body.visibility

    # Save updated metadata; update_fact also moves the fact between the ownership indexes (#16663)
    result = await kb.update_fact(fact_id=fact_id, metadata=metadata)
    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail="Failed to update visibility")

    return {
        "success": True,
        "fact_id": fact_id,
        "visibility": request_body.visibility,
    }


async def _fetch_fact_details(
    kb,
    all_fact_ids: list,
    owned_fact_ids: list,
    shared_fact_ids: list,
    limit: int,
) -> list:
    """Helper for get_my_facts. Ref: #1088.

    Fetches fact content for each ID and annotates ownership/shared flags.

    Args:
        kb: Knowledge base instance
        all_fact_ids: Deduplicated list of fact IDs to fetch
        owned_fact_ids: IDs owned by the requesting user
        shared_fact_ids: IDs shared with the requesting user
        limit: Maximum number of facts to return

    Returns:
        List of fact detail dicts
    """
    facts = []
    for fact_id in all_fact_ids[:limit]:
        fact = await asyncio.to_thread(kb.get_fact, fact_id)
        if fact:
            facts.append(
                {
                    "fact_id": fact_id,
                    "content": fact.get("content", ""),
                    "metadata": fact.get("metadata", {}),
                    "timestamp": fact.get("timestamp", ""),
                    "is_owned": fact_id in owned_fact_ids,
                    "is_shared": fact_id in shared_fact_ids,
                }
            )
    return facts


@router.get("/facts/mine", response_model=KnowledgeMyFactsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_my_facts",
    error_code_prefix="KB_OWN",
)
async def get_my_facts(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    include_shared: bool = False,
    _: dict = Depends(check_admin_permission),
):
    """Get current user's owned facts (Issue #688).

    Args:
        request: FastAPI request
        limit: Maximum results to return
        offset: Pagination offset
        include_shared: Include facts shared with user
        _: Admin permission check (required)

    Returns:
        List of facts owned by (and optionally shared with) the user
    """
    user_id = _get_user_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    kb = await get_or_create_knowledge_base()

    if not kb.ownership_manager:
        raise HTTPException(
            status_code=503,
            detail="Ownership management not available",
        )

    owned_fact_ids = await kb.ownership_manager.get_user_facts(user_id, limit=limit, offset=offset)

    shared_fact_ids = []
    if include_shared:
        shared_fact_ids = await kb.ownership_manager.get_shared_facts(user_id, limit=limit, offset=0)

    all_fact_ids = list(set(owned_fact_ids + shared_fact_ids))
    facts = await _fetch_fact_details(kb, all_fact_ids, owned_fact_ids, shared_fact_ids, limit)

    return {
        "success": True,
        "user_id": user_id,
        "owned_count": len(owned_fact_ids),
        "shared_count": len(shared_fact_ids) if include_shared else 0,
        "facts": facts,
        "total_returned": len(facts),
    }


@router.get("/facts/shared-with-me", response_model=KnowledgeSharedWithMeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_shared_facts",
    error_code_prefix="KB_OWN",
)
async def get_shared_facts(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    _: dict = Depends(check_admin_permission),
):
    """Get facts shared with current user (Issue #688).

    Args:
        request: FastAPI request
        limit: Maximum results to return
        offset: Pagination offset
        _: Admin permission check (required)

    Returns:
        List of facts shared with the user
    """
    user_id = _get_user_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    kb = await get_or_create_knowledge_base()

    if not kb.ownership_manager:
        raise HTTPException(
            status_code=503,
            detail="Ownership management not available",
        )

    # Get shared facts
    shared_fact_ids = await kb.ownership_manager.get_shared_facts(user_id, limit=limit, offset=offset)

    # Fetch fact details
    facts = []
    for fact_id in shared_fact_ids:
        fact = await asyncio.to_thread(kb.get_fact, fact_id)
        if fact:
            metadata = object_metadata(fact_id, fact.get("metadata"))
            facts.append(
                {
                    "fact_id": fact_id,
                    "content": fact.get("content", ""),
                    "metadata": metadata,
                    "timestamp": fact.get("timestamp", ""),
                    "owner_id": metadata.get("owner_id"),
                }
            )

    return {
        "success": True,
        "user_id": user_id,
        "facts": facts,
        "total_returned": len(facts),
    }
