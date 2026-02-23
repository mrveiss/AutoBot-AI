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
import logging
from typing import Dict, List, Optional

from auth_middleware import get_current_user
from backend.knowledge.ownership import VisibilityLevel
from backend.knowledge.search_filters import extract_user_context_from_request
from backend.knowledge_factory import get_or_create_knowledge_base
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/collaboration", tags=["knowledge-collaboration"])


# =============================================================================
# Pydantic Models
# =============================================================================


class KnowledgeScopeFilter(BaseModel):
    """Filter for knowledge by scope."""

    scope: Optional[VisibilityLevel] = Field(
        default=None, description="Visibility level to filter by"
    )
    organization_id: Optional[str] = Field(
        default=None, description="Organization ID filter"
    )
    group_ids: Optional[List[str]] = Field(
        default=None, description="Group IDs to filter by"
    )


class ShareKnowledgeRequest(BaseModel):
    """Request to share knowledge with users or groups."""

    user_ids: Optional[List[str]] = Field(
        default=None, description="User IDs to share with"
    )
    group_ids: Optional[List[str]] = Field(
        default=None, description="Group IDs to share with"
    )


class UpdatePermissionsRequest(BaseModel):
    """Request to update knowledge permissions."""

    visibility: VisibilityLevel = Field(description="New visibility level")
    organization_id: Optional[str] = Field(
        default=None, description="Organization ID for org-level knowledge"
    )
    group_ids: Optional[List[str]] = Field(
        default=None, description="Group IDs for group-level knowledge"
    )


class KnowledgeAccessResponse(BaseModel):
    """Response with knowledge access details."""

    fact_id: str
    owner_id: str
    visibility: VisibilityLevel
    organization_id: Optional[str] = None
    group_ids: List[str] = []
    shared_with: List[str] = []
    can_edit: bool
    can_share: bool
    can_delete: bool


# =============================================================================
# Private Helpers
# =============================================================================


async def _filter_fact_ids_by_scope(
    fact_ids: List[str], scope: VisibilityLevel, aioredis_client
) -> List[str]:
    """Helper for get_knowledge_by_scope. Ref: #1088."""
    filtered = []
    for fact_id in fact_ids:
        fact_data = await aioredis_client.hget(f"fact:{fact_id}", "metadata")
        if fact_data:
            metadata = json.loads(fact_data)
            if metadata.get("visibility") == scope:
                filtered.append(fact_id)
    return filtered


async def _fetch_facts_from_redis(
    fact_ids: List[str], aioredis_client, include_title_only: bool = False
) -> List[Dict]:
    """Helper for get_knowledge_by_scope. Ref: #1088."""
    facts = []
    for fact_id in fact_ids:
        fact_data = await aioredis_client.hgetall(f"fact:{fact_id}")
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
                entry["visibility"] = metadata.get(
                    "visibility", VisibilityLevel.PRIVATE
                )
            facts.append(entry)
    return facts


async def _fetch_and_verify_owner(fact_id: str, user_id: str, aioredis_client) -> Dict:
    """Helper for update_knowledge_permissions. Ref: #1088."""
    fact_data = await aioredis_client.hget(f"fact:{fact_id}", "metadata")
    if not fact_data:
        raise HTTPException(status_code=404, detail="Fact not found")
    if isinstance(fact_data, bytes):
        fact_data = fact_data.decode("utf-8")
    metadata = json.loads(fact_data)
    if metadata.get("owner_id") != user_id:
        raise HTTPException(
            status_code=403, detail="Only the owner can update permissions"
        )
    return metadata


def _apply_visibility_to_metadata(
    metadata: Dict,
    permissions_request: "UpdatePermissionsRequest",
    user_org_id: Optional[str],
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
    aioredis_client,
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
    await aioredis_client.hset(f"fact:{fact_id}", "metadata", json.dumps(metadata))
    logger.info(
        "Updated fact %s permissions: %s -> %s",
        fact_id,
        old_visibility,
        permissions_request.visibility,
    )


async def _fetch_fact_metadata(fact_id: str, aioredis_client) -> Dict:
    """Fetch and decode a fact's metadata hash from Redis. Ref: #1088."""
    fact_data = await aioredis_client.hget(f"fact:{fact_id}", "metadata")
    if not fact_data:
        raise HTTPException(status_code=404, detail="Fact not found")
    if isinstance(fact_data, bytes):
        fact_data = fact_data.decode("utf-8")
    return json.loads(fact_data)


async def _check_fact_access(
    fact_id: str,
    metadata: Dict,
    user_id: str,
    user_org_id: Optional[str],
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


# =============================================================================
# Endpoints - Scope-Based Retrieval
# =============================================================================


@router.get("/facts")
async def get_knowledge_by_scope(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    scope: Optional[VisibilityLevel] = Query(
        default=None, description="Filter by visibility scope"
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get knowledge facts filtered by scope.

    Issue #679: Returns facts accessible to the current user based on scope.

    Args:
        scope: Optional scope filter (system/organization/group/private/shared)
        limit: Maximum number of results
        offset: Pagination offset

    Returns:
        List of accessible knowledge facts
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Get user's organization and group memberships
        user_id, user_org_id, user_group_ids = extract_user_context_from_request(
            current_user
        )

        # Get all accessible facts
        fact_ids = await kb.ownership_manager.get_all_accessible_facts(
            user_id=user_id,
            user_org_id=user_org_id,
            user_group_ids=user_group_ids,
            limit=limit,
            offset=offset,
        )

        # If scope filter provided, filter results
        if scope:
            fact_ids = await _filter_fact_ids_by_scope(
                fact_ids, scope, kb.aioredis_client
            )

        # Fetch full fact data
        facts = await _fetch_facts_from_redis(
            fact_ids, kb.aioredis_client, include_title_only=False
        )

        return {"facts": facts, "count": len(facts), "total": len(fact_ids)}

    except Exception as e:
        logger.error("Error retrieving scoped knowledge: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve knowledge: {e}"
        )


@router.get("/facts/organization/{organization_id}")
async def get_organization_knowledge(
    organization_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get all knowledge facts for an organization.

    Issue #679: Organization-level knowledge access.

    Args:
        organization_id: Organization UUID
        limit: Maximum number of results
        offset: Pagination offset

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
            organization_id=organization_id, limit=limit, offset=offset
        )
        facts = await _fetch_facts_from_redis(
            fact_ids, kb.aioredis_client, include_title_only=True
        )
        return {"facts": facts, "count": len(facts)}

    except Exception as e:
        logger.error("Error retrieving organization knowledge: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve organization knowledge: {e}"
        )


@router.get("/facts/group/{group_id}")
async def get_group_knowledge(
    group_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get all knowledge facts for a group/team.

    Issue #679: Group-level knowledge access.

    Args:
        group_id: Group/Team UUID
        limit: Maximum number of results
        offset: Pagination offset

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
        raise HTTPException(
            status_code=403, detail="Not authorized to access this group's knowledge"
        )

    try:
        fact_ids = await kb.ownership_manager.get_group_facts(
            group_id=group_id, limit=limit, offset=offset
        )
        facts = await _fetch_facts_from_redis(
            fact_ids, kb.aioredis_client, include_title_only=True
        )
        return {"facts": facts, "count": len(facts)}

    except Exception as e:
        logger.error("Error retrieving group knowledge: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve group knowledge: {e}"
        )


# =============================================================================
# Endpoints - Sharing and Permissions
# =============================================================================


@router.post("/facts/{fact_id}/share")
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
        metadata = await _fetch_fact_metadata(fact_id, kb.aioredis_client)

        # Verify ownership
        user_id, _, _ = extract_user_context_from_request(current_user)
        if metadata.get("owner_id") != user_id:
            raise HTTPException(
                status_code=403, detail="Only the owner can share knowledge"
            )

        # Share with specified users/groups
        updated_metadata = await kb.ownership_manager.share_fact(
            fact_id=fact_id,
            user_ids=share_request.user_ids,
            group_ids=share_request.group_ids,
            fact_metadata=metadata,
        )

        # Update metadata in Redis
        await kb.aioredis_client.hset(
            f"fact:{fact_id}", "metadata", json.dumps(updated_metadata)
        )

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
        raise HTTPException(status_code=500, detail=f"Failed to share knowledge: {e}")


@router.delete("/facts/{fact_id}/share/{entity_id}")
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
        metadata = await _fetch_fact_metadata(fact_id, kb.aioredis_client)

        # Verify ownership
        user_id, _, _ = extract_user_context_from_request(current_user)
        if metadata.get("owner_id") != user_id:
            raise HTTPException(
                status_code=403, detail="Only the owner can unshare knowledge"
            )

        # Unshare from specified entity
        if entity_type == "user":
            updated_metadata = await kb.ownership_manager.unshare_fact(
                fact_id=fact_id, user_ids=[entity_id], fact_metadata=metadata
            )
        else:  # group
            updated_metadata = await kb.ownership_manager.unshare_fact(
                fact_id=fact_id, group_ids=[entity_id], fact_metadata=metadata
            )

        # Update metadata in Redis
        await kb.aioredis_client.hset(
            f"fact:{fact_id}", "metadata", json.dumps(updated_metadata)
        )

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
        raise HTTPException(status_code=500, detail=f"Failed to unshare knowledge: {e}")


@router.put("/facts/{fact_id}/permissions")
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
        metadata = await _fetch_and_verify_owner(fact_id, user_id, kb.aioredis_client)

        # Apply visibility changes and org-level guard to metadata dict
        old_visibility = metadata.get("visibility")
        metadata = _apply_visibility_to_metadata(
            metadata, permissions_request, user_org_id
        )

        # Persist Redis index updates, metadata key, and log
        await _persist_permissions_update(
            fact_id=fact_id,
            user_id=user_id,
            metadata=metadata,
            permissions_request=permissions_request,
            old_visibility=old_visibility,
            ownership_manager=kb.ownership_manager,
            aioredis_client=kb.aioredis_client,
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
        raise HTTPException(
            status_code=500, detail=f"Failed to update permissions: {e}"
        )


@router.get("/facts/{fact_id}/access")
async def get_knowledge_access_info(
    fact_id: str, request: Request, current_user: Dict = Depends(get_current_user)
):
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
        metadata = await _fetch_fact_metadata(fact_id, kb.aioredis_client)
        user_id, user_org_id, user_group_ids = extract_user_context_from_request(
            current_user
        )

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
        raise HTTPException(
            status_code=500, detail=f"Failed to get access information: {e}"
        )
