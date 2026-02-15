# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Organization Knowledge Management API

Issue #679: Organization-level knowledge policies, analytics, and controls.
"""

import logging
from typing import Dict, List, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Request
from knowledge.ownership import VisibilityLevel
from pydantic import BaseModel, Field
from user_management.models.user import User

from backend.knowledge_factory import get_or_create_knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/organization", tags=["knowledge-organization"])


# =============================================================================
# Pydantic Models
# =============================================================================


class OrganizationKnowledgePolicy(BaseModel):
    """Organization-wide knowledge policies."""

    default_visibility: VisibilityLevel = Field(
        default=VisibilityLevel.PRIVATE,
        description="Default visibility for new knowledge",
    )
    allow_user_private: bool = Field(
        default=True, description="Allow users to create private knowledge"
    )
    allow_user_shared: bool = Field(
        default=True, description="Allow users to share knowledge"
    )
    allow_user_organization: bool = Field(
        default=False, description="Allow non-admins to create org-wide knowledge"
    )
    require_approval_for_system: bool = Field(
        default=True, description="Require admin approval for system-wide knowledge"
    )
    retention_days: Optional[int] = Field(
        default=None, description="Knowledge retention period (None = indefinite)"
    )


class OrganizationKnowledgeStats(BaseModel):
    """Organization knowledge statistics."""

    organization_id: str
    total_facts: int
    by_visibility: Dict[str, int]
    by_source: Dict[str, int]
    total_size_bytes: int
    user_count: int
    team_count: int
    top_contributors: List[Dict[str, str]]


class UpdateOrganizationPolicyRequest(BaseModel):
    """Request to update organization knowledge policy."""

    policy: OrganizationKnowledgePolicy


# =============================================================================
# Endpoints - Organization Policies
# =============================================================================


@router.get("/policy")
async def get_organization_policy(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get organization knowledge policy.

    Issue #679: Organization-level knowledge policy settings.

    Returns:
        OrganizationKnowledgePolicy: Current policy settings
    """
    if not current_user.org_id:
        raise HTTPException(
            status_code=400, detail="User not associated with an organization"
        )

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Get policy from Redis or use defaults
        policy_key = f"org:policy:{current_user.org_id}"
        policy_data = await kb.aioredis_client.get(policy_key)

        if policy_data:
            import json

            if isinstance(policy_data, bytes):
                policy_data = policy_data.decode("utf-8")
            policy_dict = json.loads(policy_data)
            policy = OrganizationKnowledgePolicy(**policy_dict)
        else:
            # Return default policy
            policy = OrganizationKnowledgePolicy()

        return policy

    except Exception as e:
        logger.error("Error retrieving organization policy: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve policy: {e}")


@router.put("/policy")
async def update_organization_policy(
    policy_request: UpdateOrganizationPolicyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Update organization knowledge policy.

    Issue #679: Organization admins can configure knowledge policies.

    Args:
        policy_request: New policy settings

    Returns:
        Updated policy

    Raises:
        403: If user is not an organization admin
    """
    if not current_user.org_id:
        raise HTTPException(
            status_code=400, detail="User not associated with an organization"
        )

    # TODO: Check if user is org admin (requires org admin role check)
    # For now, assuming all users in org can update policy

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        pass

        # Store policy in Redis
        policy_key = f"org:policy:{current_user.org_id}"
        policy_json = policy_request.policy.model_dump_json()
        await kb.aioredis_client.set(policy_key, policy_json)

        logger.info("Updated organization policy for org %s", current_user.org_id)

        return policy_request.policy

    except Exception as e:
        logger.error("Error updating organization policy: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update policy: {e}")


# =============================================================================
# Endpoints - Organization Analytics
# =============================================================================


async def _analyze_organization_facts(kb, fact_ids: list) -> dict:
    """Analyze organization facts for statistics.

    Helper for get_organization_knowledge_stats() (Issue #679).
    """
    import json

    by_visibility = {}
    by_source = {}
    total_size = 0
    user_contributions = {}

    for fact_id in fact_ids:
        fact_data = await kb.aioredis_client.hgetall(f"fact:{fact_id}")
        if not fact_data:
            continue

        # Get content size
        content = fact_data.get(b"content") or fact_data.get("content")
        if content:
            if isinstance(content, bytes):
                total_size += len(content)
            else:
                total_size += len(content.encode("utf-8"))

        # Get metadata
        metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata")
        if metadata_raw:
            if isinstance(metadata_raw, bytes):
                metadata_raw = metadata_raw.decode("utf-8")
            metadata = json.loads(metadata_raw)

            # Count by visibility
            visibility = metadata.get("visibility", VisibilityLevel.PRIVATE)
            by_visibility[visibility] = by_visibility.get(visibility, 0) + 1

            # Count by source
            source = metadata.get("source_type", "unknown")
            by_source[source] = by_source.get(source, 0) + 1

            # Count by user
            owner_id = metadata.get("owner_id")
            if owner_id:
                user_contributions[owner_id] = user_contributions.get(owner_id, 0) + 1

    return {
        "by_visibility": by_visibility,
        "by_source": by_source,
        "total_size": total_size,
        "user_contributions": user_contributions,
    }


def _get_organization_team_count(current_user: User) -> int:
    """Get count of teams in user's organization.

    Helper for get_organization_knowledge_stats() (Issue #679).
    """
    return len(
        [
            m.team
            for m in current_user.team_memberships
            if m.team and m.team.org_id == current_user.org_id and not m.team.is_deleted
        ]
    )


@router.get("/stats")
async def get_organization_knowledge_stats(
    request: Request, current_user: User = Depends(get_current_user)
):
    """Get knowledge statistics for the organization.

    Issue #679: Organization-level analytics.

    Returns:
        OrganizationKnowledgeStats: Statistics and breakdowns
    """
    if not current_user.org_id:
        raise HTTPException(
            status_code=400, detail="User not associated with an organization"
        )

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        org_id = str(current_user.org_id)

        # Get all organization facts
        fact_ids = await kb.ownership_manager.get_organization_facts(
            organization_id=org_id
        )

        # Analyze facts
        analysis = await _analyze_organization_facts(kb, fact_ids)

        # Get top contributors
        top_contributors = sorted(
            [
                {"user_id": uid, "count": count}
                for uid, count in analysis["user_contributions"].items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        # Get team count from user's organization
        team_count = _get_organization_team_count(current_user)

        return OrganizationKnowledgeStats(
            organization_id=org_id,
            total_facts=len(fact_ids),
            by_visibility=analysis["by_visibility"],
            by_source=analysis["by_source"],
            total_size_bytes=analysis["total_size"],
            user_count=len(analysis["user_contributions"]),
            team_count=team_count,
            top_contributors=top_contributors,
        )

    except Exception as e:
        logger.error("Error retrieving organization stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stats: {e}")


@router.delete("/cleanup")
async def cleanup_organization_knowledge(
    request: Request,
    current_user: User = Depends(get_current_user),
    retention_days: int = 90,
):
    """Clean up old organization knowledge based on retention policy.

    Issue #679: Organization data retention management.

    Args:
        retention_days: Delete knowledge older than this many days

    Returns:
        Cleanup summary

    Raises:
        403: If user is not an organization admin
    """
    if not current_user.org_id:
        raise HTTPException(
            status_code=400, detail="User not associated with an organization"
        )

    # TODO: Check if user is org admin

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None or not kb.ownership_manager:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        import json
        from datetime import datetime, timedelta

        org_id = str(current_user.org_id)

        # Get all organization facts
        fact_ids = await kb.ownership_manager.get_organization_facts(
            organization_id=org_id
        )

        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        deleted_count = 0

        for fact_id in fact_ids:
            fact_data = await kb.aioredis_client.hgetall(f"fact:{fact_id}")
            if not fact_data:
                continue

            # Get metadata
            metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata")
            if metadata_raw:
                if isinstance(metadata_raw, bytes):
                    metadata_raw = metadata_raw.decode("utf-8")
                metadata = json.loads(metadata_raw)

                # Check creation date
                created_at_str = metadata.get("created_at")
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(
                            created_at_str.replace("Z", "+00:00")
                        )
                        if created_at < cutoff_date:
                            # Delete the fact
                            await kb.ownership_manager.cleanup_ownership_indexes(
                                fact_id, metadata
                            )
                            await kb.aioredis_client.delete(f"fact:{fact_id}")
                            deleted_count += 1
                    except (ValueError, TypeError):
                        # Skip if date parsing fails
                        pass

        logger.info(
            "Cleaned up %d facts older than %d days for org %s",
            deleted_count,
            retention_days,
            org_id,
        )

        return {
            "success": True,
            "organization_id": org_id,
            "retention_days": retention_days,
            "deleted_count": deleted_count,
            "cutoff_date": cutoff_date.isoformat(),
        }

    except Exception as e:
        logger.error("Error cleaning up organization knowledge: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to cleanup knowledge: {e}")
