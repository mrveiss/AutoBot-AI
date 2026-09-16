# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Search Filters - Scope and Permission Filtering

Issue #679: Filters search results based on hierarchical access control.
Integrates with ChromaDB metadata and ownership system.
"""

from typing import Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER

logger = get_logger(__name__)

#: What an MCP token caller may read (owner decision on #16654): platform-wide facts only,
#: by visibility or by access level. Never private, shared, group or organisation facts.
NON_PRIVATE_VISIBILITY = ("system", "public")
NON_PRIVATE_ACCESS = ("general", "autobot")


async def build_chromadb_permission_filter(
    user_id: str,
    user_org_id: str | None = None,
    user_group_ids: List[str] | None = None,
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

    # Conditions 4-6: group-level and shared facts, and facts readable by access level
    # alone, cannot be decided by a ChromaDB where (membership lives in list metadata).
    # Admit them here and let filter_search_results_by_permission's check_access make the
    # exact call: a pre-filter narrower than check_access silently drops facts the user
    # may read, and the post-filter can only remove results, never add them (#16662).
    conditions.append({"visibility": {"$in": ["shared", "group"]}})
    conditions.append({"access_level": {"$in": ["general", "autobot"]}})

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
    user_org_id: str | None = None,
    user_group_ids: List[str] | None = None,
    ownership_manager=None,
    is_admin: bool = False,
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
        is_admin: Explicit admin read (#16662). Only explicit read APIs pass it,
            never chat grounding.

    Returns:
        Filtered list of results user has access to -- empty when there is no
        ownership manager, since then no access decision can be made (#16662)
    """
    if not ownership_manager:
        logger.error("No ownership manager for permission filtering; returning no results (#16662)")
        return []

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
            is_admin=is_admin,
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
    user_org_id: str | None = None,
    user_group_ids: List[str] | None = None,
    original_where: Dict | None = None,
    is_admin: bool = False,
) -> Dict | None:
    """Augment a search request with permission-based metadata filters.

    Issue #679: Combines user's original where clause with permission filters.

    Args:
        query: Search query string
        user_id: User ID performing the search
        user_org_id: User's organization ID
        user_group_ids: List of group IDs user belongs to
        original_where: Original where clause from user request
        is_admin: Explicit admin read (#16662): no permission narrowing, so the
            post-filter's admin decision is not pre-empted. Never chat grounding.

    Returns:
        Combined where clause with permission filters
    """
    if is_admin:
        return original_where
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

    Issue #679: Helper to extract user ID, org ID, and group IDs from user data.
    Issue #934: Handle both dict (auth_middleware) and ORM User objects.

    Args:
        current_user: Dict from auth_middleware or ORM User model instance

    Returns:
        Tuple of (user_id, org_id, group_ids)
    """
    if isinstance(current_user, dict):
        user_id = current_user.get("user_id") or current_user.get("username", "")
        raw_org_id = current_user.get("org_id")
        user_org_id = str(raw_org_id) if raw_org_id else None
        # Dict-based auth does not carry team memberships
        user_group_ids = []
    else:
        user_id = str(current_user.id)
        user_org_id = str(current_user.org_id) if current_user.org_id else None
        user_group_ids = [str(m.team_id) for m in current_user.team_memberships if m.team and not m.team.is_deleted]

    return user_id, user_org_id, user_group_ids


def non_private_where(caller_where: Dict | None = None) -> Dict:
    """A ChromaDB ``where`` for an MCP token caller: non-private, unquarantined facts (#16666).

    The caller's own filter is AND-ed in, never substituted, so it can only narrow what the
    token reads. A caller asking for ``{"visibility": "private"}`` still gets nothing private.
    """
    platform_wide = {
        "$or": [
            {"visibility": {"$in": list(NON_PRIVATE_VISIBILITY)}},
            {"access_level": {"$in": list(NON_PRIVATE_ACCESS)}},
        ]
    }
    return {"$and": [platform_wide, RESEARCH_QUARANTINE_FILTER, *([caller_where] if caller_where else [])]}


def is_non_private(metadata: Dict | None) -> bool:
    """Whether an MCP token caller may read a fact with *metadata* (#16666)."""
    metadata = metadata or {}
    platform_wide = (
        metadata.get("visibility") in NON_PRIVATE_VISIBILITY or metadata.get("access_level") in NON_PRIVATE_ACCESS
    )
    return platform_wide and metadata.get("collection") != config.research_quarantine_collection


def filter_non_private_results(results: List[Dict] | None) -> List[Dict]:
    """*results* without any fact an MCP token caller may not read (#16666).

    Defence in depth behind :func:`non_private_where`: ``KB.search`` drops its ``where`` on
    the enhanced path, and this post-filter holds whatever the pre-filter did.
    """
    return [r for r in results or [] if is_non_private(r.get("metadata"))]
