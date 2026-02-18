# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Ownership and Sharing API Endpoints

Handles user ownership, visibility, and sharing for knowledge base facts.

Issue #688: User ownership model for chat-derived knowledge
"""

import logging
from typing import Optional

from auth_middleware import check_admin_permission
from backend.api.knowledge_models import ShareFactRequest, UpdateVisibilityRequest
from backend.knowledge_factory import get_or_create_knowledge_base
from fastapi import APIRouter, Depends, HTTPException, Request

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge_ownership"])


def _get_user_from_request(request: Request) -> Optional[str]:
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
        HTTPException: 404 if not found, 403 if no access
    """
    fact = await kb.get_fact(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    # Check access
    if not kb.ownership_manager:
        # If ownership manager not initialized, allow access (backward compat)
        return fact

    metadata = fact.get("metadata", {})
    has_access = await kb.ownership_manager.check_access(fact_id, user_id, metadata)

    if not has_access:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this fact",
        )

    return fact


@router.post("/api/knowledge/facts/{fact_id}/share")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_fact",
    error_code_prefix="KB_OWN",
)
async def share_fact(
    fact_id: str,
    request_body: ShareFactRequest,
    request: Request,
    _: dict = Depends(check_admin_permission),
):
    """Share a fact with additional users (Issue #688).

    Args:
        fact_id: Fact ID to share
        request_body: Share request with user_ids
        request: FastAPI request
        _: Admin permission check (required)

    Returns:
        Success response with updated sharing info
    """
    user_id = _get_user_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    kb = await get_or_create_knowledge_base()

    # Get fact and verify ownership
    fact = await _get_fact_with_ownership(kb, fact_id, user_id)

    # Only owner can share facts
    owner_id = fact.get("metadata", {}).get("owner_id")
    if owner_id and owner_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the owner can share this fact",
        )

    # Update sharing
    if not kb.ownership_manager:
        raise HTTPException(
            status_code=503,
            detail="Ownership management not available",
        )

    metadata = fact.get("metadata", {})
    updated_metadata = await kb.ownership_manager.share_fact(
        fact_id, request_body.user_ids, metadata
    )

    # Save updated metadata
    await kb.update_fact(fact_id=fact_id, metadata=updated_metadata)

    return {
        "success": True,
        "fact_id": fact_id,
        "shared_with": updated_metadata.get("shared_with", []),
        "visibility": updated_metadata.get("visibility"),
    }


@router.delete("/api/knowledge/facts/{fact_id}/share/{user_id_to_remove}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unshare_fact",
    error_code_prefix="KB_OWN",
)
async def unshare_fact(
    fact_id: str,
    user_id_to_remove: str,
    request: Request,
    _: dict = Depends(check_admin_permission),
):
    """Remove user from fact sharing list (Issue #688).

    Args:
        fact_id: Fact ID to unshare
        user_id_to_remove: User ID to remove from sharing
        request: FastAPI request
        _: Admin permission check (required)

    Returns:
        Success response with updated sharing info
    """
    user_id = _get_user_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    kb = await get_or_create_knowledge_base()

    # Get fact and verify ownership
    fact = await _get_fact_with_ownership(kb, fact_id, user_id)

    # Only owner can unshare facts
    owner_id = fact.get("metadata", {}).get("owner_id")
    if owner_id and owner_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the owner can unshare this fact",
        )

    # Update sharing
    if not kb.ownership_manager:
        raise HTTPException(
            status_code=503,
            detail="Ownership management not available",
        )

    metadata = fact.get("metadata", {})
    updated_metadata = await kb.ownership_manager.unshare_fact(
        fact_id, [user_id_to_remove], metadata
    )

    # Save updated metadata
    await kb.update_fact(fact_id=fact_id, metadata=updated_metadata)

    return {
        "success": True,
        "fact_id": fact_id,
        "shared_with": updated_metadata.get("shared_with", []),
        "visibility": updated_metadata.get("visibility"),
    }


@router.put("/api/knowledge/facts/{fact_id}/visibility")
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
    owner_id = fact.get("metadata", {}).get("owner_id")
    if owner_id and owner_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the owner can change visibility",
        )

    # Update visibility in metadata
    metadata = fact.get("metadata", {})
    metadata["visibility"] = request_body.visibility

    # Save updated metadata
    await kb.update_fact(fact_id=fact_id, metadata=metadata)

    return {
        "success": True,
        "fact_id": fact_id,
        "visibility": request_body.visibility,
    }


@router.get("/api/knowledge/facts/mine")
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

    # Get owned facts
    owned_fact_ids = await kb.ownership_manager.get_user_facts(
        user_id, limit=limit, offset=offset
    )

    # Get shared facts if requested
    shared_fact_ids = []
    if include_shared:
        shared_fact_ids = await kb.ownership_manager.get_shared_facts(
            user_id, limit=limit, offset=0
        )

    # Combine and deduplicate
    all_fact_ids = list(set(owned_fact_ids + shared_fact_ids))

    # Fetch fact details
    facts = []
    for fact_id in all_fact_ids[:limit]:
        fact = await kb.get_fact(fact_id)
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

    return {
        "success": True,
        "user_id": user_id,
        "owned_count": len(owned_fact_ids),
        "shared_count": len(shared_fact_ids) if include_shared else 0,
        "facts": facts,
        "total_returned": len(facts),
    }


@router.get("/api/knowledge/facts/shared-with-me")
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
    shared_fact_ids = await kb.ownership_manager.get_shared_facts(
        user_id, limit=limit, offset=offset
    )

    # Fetch fact details
    facts = []
    for fact_id in shared_fact_ids:
        fact = await kb.get_fact(fact_id)
        if fact:
            facts.append(
                {
                    "fact_id": fact_id,
                    "content": fact.get("content", ""),
                    "metadata": fact.get("metadata", {}),
                    "timestamp": fact.get("timestamp", ""),
                    "owner_id": fact.get("metadata", {}).get("owner_id"),
                }
            )

    return {
        "success": True,
        "user_id": user_id,
        "facts": facts,
        "total_returned": len(facts),
    }
