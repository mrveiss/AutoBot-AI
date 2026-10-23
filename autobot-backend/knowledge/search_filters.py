# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Search Filters - Scope and Permission Filtering

Issue #679: Filters search results based on hierarchical access control.
Integrates with ChromaDB metadata and ownership system.
"""

import asyncio
import json
from typing import Dict, List

from fastapi import HTTPException

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from autobot_shared.scoping import Principal
from autobot_shared.ssot_config import config
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.where_combine import and_where

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


def _user_field(user, name: str):
    """Read *name* from a mapping user or an ORM/object user (``.get`` or attribute)."""
    getter = getattr(user, "get", None)
    return getter(name) if callable(getter) else getattr(user, name, None)


async def can_read_fact(
    ownership_manager,
    fact_id: str,
    metadata: Dict,
    current_user=None,
    *,
    user_id: str | None = None,
    is_admin: bool | None = None,
) -> bool:
    """Whether a caller may read a fact: the one per-fact read decision (#18184).

    Two call shapes. With ``current_user`` the user, org, groups and admin role are
    resolved from it (``is_admin`` may still override). With a bare ``user_id`` -- for
    routes already behind an admin dependency, which carry no user dict -- the id and
    ``is_admin`` pass through and the caller has no org or groups. An admin reads any
    fact here (#16662); only explicit read APIs call this.
    """
    org_id, group_ids = None, []
    if current_user is not None:
        user_id, org_id, group_ids = extract_user_context_from_request(current_user)
        if is_admin is None:
            is_admin = is_admin_role(_user_field(current_user, "role"))
    return await ownership_manager.check_access(
        fact_id=fact_id,
        user_id=user_id,
        fact_metadata=metadata,
        user_org_id=org_id,
        user_group_ids=group_ids,
        is_admin=bool(is_admin),
    )


def fact_not_found() -> HTTPException:
    """The one answer for a fact that is missing or that the caller may not read (#18220).

    A non-reader must not be able to tell an existing fact from an absent one, so both
    carry this exact status and detail.
    """
    return HTTPException(status_code=404, detail="Fact not found")


def object_metadata(fact_id: str, metadata) -> Dict:
    """A fact's metadata as a dict; anything that is not an object reads as ``{}`` (#18220).

    ``{}`` has no owner and private visibility, so only an admin is let through. The warning
    names the fact id and the JSON type, never the content.
    """
    if isinstance(metadata, dict):
        return metadata
    if metadata:  # an absent or empty value is an ordinary fact with no metadata
        logger.warning(
            "Fact %s has non-object metadata (%s); treating it as unreadable", fact_id, type(metadata).__name__
        )
    return {}


def parse_fact_metadata(fact_id: str, raw, *, strict: bool = False) -> Dict | None:
    """Decode a stored metadata JSON value into a dict (#18220).

    Anything unparseable or non-object reads as ``{}``, with a WARNING naming the fact id. With
    ``strict`` such a value returns ``None`` instead, so a batch job can skip the fact and go on.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        parsed = raw
    if strict:
        if isinstance(parsed, dict):
            return parsed
        logger.warning("Fact %s has non-object metadata (%s); skipping it", fact_id, type(parsed).__name__)
        return None
    return object_metadata(fact_id, parsed)


async def require_fact_owner(ownership_manager, fact_id: str, metadata: Dict, current_user, detail: str) -> None:
    """Pass the owner; a non-owner reader gets 403 *detail*, a non-reader the missing-fact 404 (#18220)."""
    user_id, _, _ = extract_user_context_from_request(current_user)
    if metadata.get("owner_id") == user_id:
        return
    if not await can_read_fact(ownership_manager, fact_id, metadata, current_user):
        raise fact_not_found()
    raise HTTPException(status_code=403, detail=detail)


async def _authorize_fact(kb, fact_id: str, current_user, *, write: bool) -> Dict:
    """Load a fact and require the read (or write) decision to allow the caller (#18184, #18220).

    503 without an ownership manager (no decision can be made, #16662). 404 when the fact is
    absent *or the caller cannot read it* -- identical, so ids cannot be probed. 403 only for a
    caller who can read the fact but may not write it. Returns the fact dict.
    """
    if not getattr(kb, "ownership_manager", None):
        raise HTTPException(status_code=503, detail="Knowledge base not available")
    fact = await asyncio.to_thread(kb.get_fact, fact_id)  # get_fact is synchronous
    if not fact:
        raise fact_not_found()
    metadata = object_metadata(fact_id, fact.get("metadata"))
    if write and can_write_fact(metadata, current_user):
        return fact
    if not await can_read_fact(kb.ownership_manager, fact_id, metadata, current_user):
        raise fact_not_found()
    if write:
        raise HTTPException(status_code=403, detail="Access denied")
    return fact


async def authorize_fact_read(kb, fact_id: str, current_user) -> Dict:
    """Load a fact through the canonical KB read and require that the caller may read it (#18184)."""
    return await _authorize_fact(kb, fact_id, current_user, write=False)


def can_write_fact(metadata: Dict, current_user) -> bool:
    """Whether a caller may write a fact: the one per-fact write decision (#18184).

    The KB's only per-fact write grant is ownership -- the ``can_edit`` the access-info route
    reports is ``owner_id == user`` -- and an admin writes any fact, resolved from the role the
    same way :func:`can_read_fact` does. A fact with no owner is writable by an admin only.
    """
    if is_admin_role(_user_field(current_user, "role")):
        return True
    user_id, _, _ = extract_user_context_from_request(current_user)
    owner_id = metadata.get("owner_id")
    return bool(owner_id) and owner_id == user_id


async def authorize_fact_write(kb, fact_id: str, current_user) -> Dict:
    """Load a fact and require that the caller may write it, whether or not they can read it (#18184)."""
    return await _authorize_fact(kb, fact_id, current_user, write=True)


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
    return and_where(platform_wide, RESEARCH_QUARANTINE_FILTER, caller_where)  # type: ignore[return-value]


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


class _SystemScopeSentinel:
    """Type of :data:`SYSTEM_SCOPE` -- deliberately not ``str`` (#16664).

    A plain string sentinel would equal a username that spells it. A non-``str``
    singleton compared with ``is`` can never equal anything a caller supplies
    (the same shape as ``memory.verbatim_store.UNSCOPED_ALL_USERS``).
    """

    def __repr__(self) -> str:
        return "SYSTEM_SCOPE"


#: The one explicit way to read the KB with no user (background, system, MCP stdio): it sees
#: non-private facts only, via :func:`filter_non_private_results`. A missing principal is
#: never read as this -- it raises (:func:`require_kb_principal`).
SYSTEM_SCOPE = _SystemScopeSentinel()

KbPrincipal = Principal | _SystemScopeSentinel


def kb_principal(current_user) -> Principal:
    """The visibility principal of an authenticated caller (#16664).

    Built from :func:`extract_user_context_from_request`, so the user, org and groups are the
    ones every other KB read path resolves. There is deliberately no admin flag: RAG and chat
    grounding never bypass visibility.
    """
    user_id, org_id, group_ids = extract_user_context_from_request(current_user)
    return _authenticated_principal(user_id, org_id, group_ids)


def _authenticated_principal(user_id, org_id, group_ids) -> Principal:
    """The one place a KB ``Principal`` is constructed; no user id is refused (#16664)."""
    if not user_id:
        raise ValueError("kb_principal needs an authenticated user; use SYSTEM_SCOPE for a no-user read")
    return Principal(user_id=user_id, company_id=org_id, group_ids=frozenset(group_ids), is_authenticated=True)


def kb_principal_from_tenant(tenant) -> Principal:
    """The visibility principal of a verified ``TenantContext`` (#16664, #18825).

    For routes that take ``get_tenant_context`` and no user dict. Same ``Principal`` as
    :func:`kb_principal`: user and org come from the verified context; a tenant context carries
    no team memberships, so ``group_ids`` is empty (as for dict-based auth). No admin bypass.
    """
    user_id = str(tenant.user_id) if getattr(tenant, "user_id", None) else None
    org_id = str(tenant.org_id) if getattr(tenant, "org_id", None) else None
    return _authenticated_principal(user_id, org_id, [])


def principal_for_identity(user_id: str | None, org_id: str | None = None) -> KbPrincipal:
    """The principal for a verified identity; no user id reads as :data:`SYSTEM_SCOPE` (#16664).

    For callers that hold ids, not a user object (a chat session). The fallback is the
    non-private-only scope, never a wider one.
    """
    if not user_id:
        return SYSTEM_SCOPE
    return kb_principal({"user_id": user_id, "org_id": org_id})


def require_kb_principal(principal) -> KbPrincipal:
    """Return *principal* if it is a real one: ``None`` -> ValueError, any other type -> TypeError (#16664)."""
    if principal is None:
        raise ValueError("a KB read needs a principal; pass SYSTEM_SCOPE explicitly for a no-user read")
    if principal is SYSTEM_SCOPE or isinstance(principal, Principal):
        return principal
    raise TypeError(f"principal must be a Principal or SYSTEM_SCOPE, not {type(principal).__name__}")


async def filter_for_principal(results: List[Dict], principal: KbPrincipal, ownership_manager) -> List[Dict]:
    """*results* the principal may read: the one result filter for RAG and chat grounding (#16664).

    ``SYSTEM_SCOPE`` keeps non-private facts only; a ``Principal`` goes through
    :func:`filter_search_results_by_permission` with no admin bypass.
    """
    principal = require_kb_principal(principal)
    if principal is SYSTEM_SCOPE:
        return filter_non_private_results(results)
    return await filter_search_results_by_permission(
        results,
        principal.user_id,
        principal.company_id,
        list(principal.group_ids),
        ownership_manager=ownership_manager,
    )
