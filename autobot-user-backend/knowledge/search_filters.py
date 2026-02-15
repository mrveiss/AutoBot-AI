# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Search Filters - Scope and Permission Filtering

Issue #679: Filters search results based on hierarchical access control.
Integrates with ChromaDB metadata and ownership system.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


async def build_chromadb_permission_filter(
    user_id: str,
    user_org_id: Optional[str] = None,
    user_group_ids: Optional[List[str]] = None,
) -> Dict:
    """Build ChromaDB where filter for permission-based search.

    Issue #679: Constructs metadata filters for ChromaDB queries.

    Args:
        user_id: User ID performing the search
        user_org_id: User's organization ID
        user_group_ids: List of group IDs user belongs to

    Returns:
        ChromaDB where clause dict for filtering by permissions
    """
    user_group_ids = user_group_ids or []

    # Build OR conditions for accessible facts
    # User can access if:
    # 1. Owner of the fact
    # 2. Fact is system/public visibility
    # 3. Fact is organization-level and user belongs to org
    # 4. Fact is group-level and user belongs to group
    # 5. Fact is explicitly shared with user

    # ChromaDB supports $or, $and operators
    conditions = []

    # Condition 1: User is owner
    conditions.append({"owner_id": user_id})

    # Condition 2: System/Public visibility
    conditions.append({"visibility": "system"})
    conditions.append({"visibility": "public"})

    # Condition 3: Organization-level
    if user_org_id:
        conditions.append(
            {
                "$and": [
                    {"visibility": "organization"},
                    {"organization_id": user_org_id},
                ]
            }
        )

    # Condition 4: Group-level (check if user belongs to ANY of the fact's groups)
    # Note: ChromaDB doesn't support array intersection, so we can't directly filter
    # group facts. We'll filter these in post-processing.

    # Condition 5: Explicitly shared (also requires post-processing)

    # Build final filter
    if len(conditions) > 1:
        where_clause = {"$or": conditions}
    elif len(conditions) == 1:
        where_clause = conditions[0]
    else:
        # Fallback: owner only
        where_clause = {"owner_id": user_id}

    return where_clause


async def filter_search_results_by_permission(
    results: List[Dict],
    user_id: str,
    user_org_id: Optional[str] = None,
    user_group_ids: Optional[List[str]] = None,
    ownership_manager=None,
) -> List[Dict]:
    """Filter search results to only include facts user has access to.

    Issue #679: Post-processing filter for results that ChromaDB can't filter.
    Handles group-level and shared fact filtering.

    Args:
        results: List of search result dicts
        user_id: User ID performing the search
        user_org_id: User's organization ID
        user_group_ids: List of group IDs user belongs to
        ownership_manager: KnowledgeOwnership instance for access checks

    Returns:
        Filtered list of results user has access to
    """
    if not ownership_manager:
        logger.warning("No ownership manager provided for permission filtering")
        return results

    user_group_ids = user_group_ids or []
    filtered_results = []

    for result in results:
        # Get fact metadata
        metadata = result.get("metadata", {})

        # If no metadata, skip (shouldn't happen but be defensive)
        if not metadata:
            continue

        # Check access using ownership manager
        has_access = await ownership_manager.check_access(
            fact_id=result.get("id", ""),
            user_id=user_id,
            fact_metadata=metadata,
            user_org_id=user_org_id,
            user_group_ids=user_group_ids,
        )

        if has_access:
            filtered_results.append(result)

    logger.debug(
        "Filtered search results: %d/%d accessible to user %s",
        len(filtered_results),
        len(results),
        user_id,
    )

    return filtered_results


async def augment_search_request_with_permissions(
    query: str,
    user_id: str,
    user_org_id: Optional[str] = None,
    user_group_ids: Optional[List[str]] = None,
    original_where: Optional[Dict] = None,
) -> Dict:
    """Augment a search request with permission-based metadata filters.

    Issue #679: Combines user's original where clause with permission filters.

    Args:
        query: Search query string
        user_id: User ID performing the search
        user_org_id: User's organization ID
        user_group_ids: List of group IDs user belongs to
        original_where: Original where clause from user request

    Returns:
        Combined where clause with permission filters
    """
    # Build permission filter
    permission_filter = await build_chromadb_permission_filter(
        user_id=user_id, user_org_id=user_org_id, user_group_ids=user_group_ids
    )

    # Combine with original filter if provided
    if original_where:
        combined_where = {"$and": [original_where, permission_filter]}
    else:
        combined_where = permission_filter

    return combined_where


def extract_user_context_from_request(current_user) -> tuple:
    """Extract user context for permission filtering.

    Issue #679: Helper to extract user ID, org ID, and group IDs from User model.

    Args:
        current_user: User model instance

    Returns:
        Tuple of (user_id, org_id, group_ids)
    """
    user_id = str(current_user.id)
    user_org_id = str(current_user.org_id) if current_user.org_id else None

    # Extract group IDs from team memberships
    user_group_ids = [
        str(m.team_id)
        for m in current_user.team_memberships
        if m.team and not m.team.is_deleted
    ]

    return user_id, user_org_id, user_group_ids
