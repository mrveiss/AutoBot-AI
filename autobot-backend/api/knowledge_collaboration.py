# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Collaboration API - Multi-Level Access Control

Issue #679: Hierarchical knowledge access control system supporting:
- System-wide knowledge (platform-level)
- Organization knowledge (company-wide)
- Group knowledge (team-level)
- User knowledge (private)
- Shared knowledge (explicit sharing)
"""

import json
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.schemas_knowledge import (
    KnowledgeAccessInfoResponse,
    KnowledgePermissionsUpdateResponse,
    KnowledgeScopedFactsResponse,
    KnowledgeShareResponse,
    KnowledgeUnshareResponse,
    ShareKnowledgeRequest,
    UpdatePermissionsRequest,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.pagination import PaginationParams
from knowledge.ownership import VisibilityLevel
from knowledge.search_filters import extract_user_context_from_request
from knowledge_factory import get_or_create_knowledge_base

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge/collaboration", tags=["knowledge-collaboration"])


# =============================================================================
# Pydantic Models
# =============================================================================


# =============================================================================
# Private Helpers
# =============================================================================


async def _filter_fact_ids_by_scope(fact_ids: List[str], scope: VisibilityLevel, redis) -> List[str]:
    """Helper for get_knowledge_by_scope. Ref: #1088."""
    filtered = []
    for fact_id in fact_ids:
        fact_data = await redis.hget(f"fact:{fact_id}", "metadata")
        if fact_data:
            metadata = json.loads(fact_data)
            if metadata.get("visibility") == scope:
                filtered.append(fact_id)
    return filtered


async def _fetch_facts_from_redis(fact_ids: List[str], redis, include_title_only: bool = False) -> List[Dict]:
    """Helper for get_knowledge_by_scope. Ref: #1088."""
    facts = []
    for fact_id in fact_ids:
        fact_data = await redis.hgetall(f"fact:{fact_id}")
        if fact_data:
            content = fact_data.get(b"content") or fact_data.get("content")
            metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata")

            if isinstance(content, bytes):
                content = content.decode("utf-8")
            if isinstance(metadata_raw, bytes):
                metadata_raw = metadata_raw.decode("utf-8")

            metadata = json.loads(metadata_raw) if metadata_raw else {}

            entry: Dict = {
                "id": fact_id,
                "content": content,
                "metadata": metadata,
                "title": metadata.get("title", "Untitled"),
            }
            if not include_title_only:
                entry["visibility"] = metadata.get("visibility", VisibilityLevel.PRIVATE)
            facts.append(entry)
    return facts


async def _fetch_and_verify_owner(fact_id: str, user_id: str, redis) -> Dict:
    """Helper for update_knowledge_permissions. Ref: #1088."""
    fact_data = await redis.hget(f"fact:{fact_id}", "metadata")
    if not fact_data:
        raise HTTPException(status_code=404, detail="Fact not found")
    if isinstance(fact_data, bytes):
        fact_data = fact_data.decode("utf-8")
    metadata = json.loads(fact_data)
    if metadata.get("owner_id") != user_id:
        raise HTTPException(status_code=403, detail="Only the owner can update permissions")
    return metadata


def _apply_visibility_to_metadata(
    metadata: Dict,
    permissions_request: "UpdatePermissionsRequest",
    user_org_id: str | None,
) -> Dict:
    """Helper for update_knowledge_permissions. Ref: #1088."""
    if permissions_request.visibility == VisibilityLevel.ORGANIZATION:
        if not user_org_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot create organization knowledge without organization membership",
            )
        permissions_request.organization_id = user_org_id

    metadata["visibility"] = permissions_request.visibility
    metadata["organization_id"] = permissions_request.organization_id
    metadata["group_ids"] = permissions_request.group_ids or []
    return metadata


async def _persist_permissions_update(
    fact_id: str,
    user_id: str,
    metadata: Dict,
    permissions_request: "UpdatePermissionsRequest",
    old_visibility: str,
    ownership_manager,
    redis,
) -> None:
    """Helper for update_knowledge_permissions. Ref: #1088."""
    await ownership_manager.set_owner(
        fact_id=fact_id,
        owner_id=user_id,
        visibility=permissions_request.visibility,
        source_type=metadata.get("source_type", "manual"),
        shared_with=metadata.get("shared_with", []),
        organization_id=permissions_request.organization_id,
        group_ids=permissions_request.group_ids or [],
    )
    await redis.hset(f"fact:{fact_id}", "metadata", json.dumps(metadata))
    logger.info(
        "Updated fact %s permissions: %s -> %s",
        fact_id,
        old_visibility,
        permissions_request.visibility,
    )


async def _fetch_fact_metadata(fact_id: str, redis) -> Dict:
    """Fetch and decode a fact's metadata hash from Redis. Ref: #1088."""
    fact_data = await redis.hget(f"fact:{fact_id}", "metadata")
    if not fact_data:
        raise HTTPException(status_code=404, detail="Fact not found")
    if isinstance(fact_data, bytes):
        fact_data = fact_data.decode("utf-8")
    return json.loads(fact_data)


async def _check_fact_access(
    fact_id: str,
    metadata: Dict,
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    ownership_manager,
) -> bool:
    """Check whether a user has access to a fact. Ref: #1088."""
    return await ownership_manager.check_access(
        fact_id=fact_id,
        user_id=user_id,
        fact_metadata=metadata,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
    )


def _build_access_response(fact_id: str, metadata: Dict, user_id: str) -> Dict:
    """Build the access-info response dict for a fact. Ref: #1088."""
    is_owner = metadata.get("owner_id") == user_id
    return {
        "fact_id": fact_id,
        "owner_id": metadata.get("owner_id"),
        "visibility": metadata.get("visibility", VisibilityLevel.PRIVATE),
        "organization_id": metadata.get("organization_id"),
        "group_ids": metadata.get("group_ids", []),
        "shared_with": metadata.get("shared_with", []),
        "can_edit": is_owner,
        "can_share": is_owner,
        "can_delete": is_owner,
        "has_access": True,
    }


async def _verify_fact_ownership(fact_id: str, user_id: str, redis, action_label: str) -> Dict:
    """Fetch metadata and assert the caller is the owner. Ref: #1088."""
    metadata = await _fetch_fact_metadata(fact_id, redis)
    if metadata.get("owner_id") != user_id:
        raise HTTPException(status_code=403, detail=f"Only the owner can {action_label} knowledge")
    return metadata


async def _unshare_fact_by_entity(
    fact_id: str, entity_id: str, entity_type: str, metadata: Dict, ownership_manager
) -> Dict:
    """Dispatch unshare_fact for user or group entity. Helper for unshare_knowledge. Ref: #1088."""
    if entity_type == "user":
        return await ownership_manager.unshare_fact(fact_id=fact_id, user_ids=[entity_id], fact_metadata=metadata)
    return await ownership_manager.unshare_fact(fact_id=fact_id, group_ids=[entity_id], fact_metadata=metadata)


# =============================================================================
# Endpoints - Scope-Based Retrieval
# =============================================================================


@router.get("/facts", response_model=KnowledgeScopedFactsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_by_scope",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def get_knowledge_by_scope(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    scope: VisibilityLevel | None = Query(default=None, description="Filter by visibility scope"),
    pagination: PaginationParams = Depends(),
):
    """Get knowledge facts filtered by scope.

    Issue #679: Returns facts accessible to the current user based on scope.

    Args:
        scope: Optional scope filter (system/organization/group/private/shared)
        pagination: Limit and offset for result pagination

    Returns:
        List of accessible knowledge facts
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Get user's organization and group memberships
        user_id, user_org_id, user_group_ids = extract_user_context_from_request(current_user)

        # Get all accessible facts
        fact_ids = await kb.ownership_manager.get_all_accessible_facts(
            user_id=user_id,
            user_org_id=user_org_id,
            user_group_ids=user_group_ids,
            limit=pagination.limit,
            offset=pagination.offset,
        )

        # If scope filter provided, filter results
        if scope:
            fact_ids = await _filter_fact_ids_by_scope(fact_ids, scope, kb.redis())

        # Fetch full fact data
        facts = await _fetch_facts_from_redis(fact_ids, kb.redis(), include_title_only=False)

        return {"facts": facts, "count": len(facts), "total": len(fact_ids)}

    except Exception as e:
        logger.error("Error retrieving scoped knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/facts/organization/{organization_id}", response_model=KnowledgeScopedFactsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_organization_knowledge",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def get_organization_knowledge(
    organization_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    pagination: PaginationParams = Depends(),
):
    """Get all knowledge facts for an organization.

    Issue #679: Organization-level knowledge access.

    Args:
        organization_id: Organization UUID
        pagination: Limit and offset for result pagination

    Returns:
        List of organization knowledge facts

    Raises:
        403: If user is not a member of the organization
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    # Verify user belongs to organization
    _, user_org_id, _ = extract_user_context_from_request(current_user)
    if user_org_id != organization_id:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this organization's knowledge",
        )

    try:
        fact_ids = await kb.ownership_manager.get_organization_facts(
            organization_id=organization_id,
            limit=pagination.limit,
            offset=pagination.offset,
        )
        facts = await _fetch_facts_from_redis(fact_ids, kb.redis(), include_title_only=True)
        return {"facts": facts, "count": len(facts)}

    except Exception as e:
        logger.error("Error retrieving organization knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/facts/group/{group_id}", response_model=KnowledgeScopedFactsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_group_knowledge",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def get_group_knowledge(
    group_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    pagination: PaginationParams = Depends(),
):
    """Get all knowledge facts for a group/team.

    Issue #679: Group-level knowledge access.

    Args:
        group_id: Group/Team UUID
        pagination: Limit and offset for result pagination

    Returns:
        List of group knowledge facts

    Raises:
        403: If user is not a member of the group
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    # Verify user is a member of the group
    _, _, user_group_ids = extract_user_context_from_request(current_user)
    if group_id not in user_group_ids:
        raise HTTPException(status_code=403, detail="Not authorized to access this group's knowledge")

    try:
        fact_ids = await kb.ownership_manager.get_group_facts(
            group_id=group_id, limit=pagination.limit, offset=pagination.offset
        )
        facts = await _fetch_facts_from_redis(fact_ids, kb.redis(), include_title_only=True)
        return {"facts": facts, "count": len(facts)}

    except Exception as e:
        logger.error("Error retrieving group knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Endpoints - Sharing and Permissions
# =============================================================================


@router.post("/facts/{fact_id}/share", response_model=KnowledgeShareResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="share_knowledge",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def share_knowledge(
    fact_id: str,
    share_request: ShareKnowledgeRequest,
    request: Request,
    current_user: Dict = Depends(get_current_user),
):
    """Share a knowledge fact with users or groups.

    Issue #679: Multi-entity sharing support.

    Args:
        fact_id: Fact ID to share
        share_request: Users and/or groups to share with

    Returns:
        Updated fact metadata

    Raises:
        403: If user is not the owner
        404: If fact not found
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        user_id, _, _ = extract_user_context_from_request(current_user)
        metadata = await _verify_fact_ownership(fact_id, user_id, kb.redis(), "share")

        updated_metadata = await kb.ownership_manager.share_fact(
            fact_id=fact_id,
            user_ids=share_request.user_ids,
            group_ids=share_request.group_ids,
            fact_metadata=metadata,
        )

        await kb.redis().hset(f"fact:{fact_id}", "metadata", json.dumps(updated_metadata))

        logger.info(
            "Shared fact %s with %d users and %d groups",
            fact_id,
            len(share_request.user_ids or []),
            len(share_request.group_ids or []),
        )

        return {
            "success": True,
            "fact_id": fact_id,
            "visibility": updated_metadata.get("visibility"),
            "shared_with": updated_metadata.get("shared_with", []),
            "group_ids": updated_metadata.get("group_ids", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sharing knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/facts/{fact_id}/share/{entity_id}", response_model=KnowledgeUnshareResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unshare_knowledge",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def unshare_knowledge(
    fact_id: str,
    entity_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    entity_type: str = Query(..., pattern="^(user|group)$"),
):
    """Revoke access to a knowledge fact from a user or group.

    Issue #679: Granular unsharing support.

    Args:
        fact_id: Fact ID
        entity_id: User ID or Group ID to revoke access from
        entity_type: "user" or "group"

    Returns:
        Updated fact metadata

    Raises:
        403: If user is not the owner
        404: If fact not found
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        user_id, _, _ = extract_user_context_from_request(current_user)
        metadata = await _verify_fact_ownership(fact_id, user_id, kb.redis(), "unshare")

        updated_metadata = await _unshare_fact_by_entity(
            fact_id, entity_id, entity_type, metadata, kb.ownership_manager
        )

        await kb.redis().hset(f"fact:{fact_id}", "metadata", json.dumps(updated_metadata))

        logger.info("Unshared fact %s from %s %s", fact_id, entity_type, entity_id)

        return {
            "success": True,
            "fact_id": fact_id,
            "visibility": updated_metadata.get("visibility"),
            "shared_with": updated_metadata.get("shared_with", []),
            "group_ids": updated_metadata.get("group_ids", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error unsharing knowledge: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/facts/{fact_id}/permissions", response_model=KnowledgePermissionsUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_knowledge_permissions",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def update_knowledge_permissions(
    fact_id: str,
    permissions_request: UpdatePermissionsRequest,
    request: Request,
    current_user: Dict = Depends(get_current_user),
):
    """Update knowledge fact permissions and visibility.

    Issue #679: Change scope level (private/group/organization/system).

    Args:
        fact_id: Fact ID
        permissions_request: New permissions settings

    Returns:
        Updated fact metadata

    Raises:
        403: If user is not the owner or lacks permissions
        404: If fact not found
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Fetch metadata and verify the caller is the owner
        user_id, user_org_id, _ = extract_user_context_from_request(current_user)
        metadata = await _fetch_and_verify_owner(fact_id, user_id, kb.redis())

        # Apply visibility changes and org-level guard to metadata dict
        old_visibility = metadata.get("visibility")
        metadata = _apply_visibility_to_metadata(metadata, permissions_request, user_org_id)

        # Persist Redis index updates, metadata key, and log
        await _persist_permissions_update(
            fact_id=fact_id,
            user_id=user_id,
            metadata=metadata,
            permissions_request=permissions_request,
            old_visibility=old_visibility,
            ownership_manager=kb.ownership_manager,
            redis=kb.redis(),
        )

        return {
            "success": True,
            "fact_id": fact_id,
            "visibility": metadata.get("visibility"),
            "organization_id": metadata.get("organization_id"),
            "group_ids": metadata.get("group_ids", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating knowledge permissions: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/facts/{fact_id}/access", response_model=KnowledgeAccessInfoResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_access_info",
    error_code_prefix="KNOWLEDGE_COLLABORATION",
)
async def get_knowledge_access_info(fact_id: str, request: Request, current_user: Dict = Depends(get_current_user)):
    """Get access information for a knowledge fact.

    Issue #679: Returns who has access and what permissions they have.

    Args:
        fact_id: Fact ID

    Returns:
        Access information including visibility, shared users/groups, and user permissions

    Raises:
        404: If fact not found
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        metadata = await _fetch_fact_metadata(fact_id, kb.redis())
        user_id, user_org_id, user_group_ids = extract_user_context_from_request(current_user)

        has_access = await _check_fact_access(
            fact_id=fact_id,
            metadata=metadata,
            user_id=user_id,
            user_org_id=user_org_id,
            user_group_ids=user_group_ids,
            ownership_manager=kb.ownership_manager,
        )
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")

        return _build_access_response(fact_id, metadata, user_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting knowledge access info: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
