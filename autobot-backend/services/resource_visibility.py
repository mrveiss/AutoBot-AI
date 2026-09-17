# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Compose is_visible() + grant lookup into the single access entry point (#11277).

Includes a small per-process decision cache keyed by (resource, principal); the
spec's company-keyed cache — invalidated on grant/scope change via invalidate().
"""

from sqlalchemy.ext.asyncio import AsyncSession

import services.resource_grant_store as store
from autobot_shared.logging_manager import get_logger
from autobot_shared.scoping.visibility import Principal, ResourceDescriptor, is_visible
from models.resource_grant import ResourceGrant
from services.audit_logger import audit_log

logger = get_logger(__name__)

# (resource_type, resource_id) -> { principal_key: bool }
_cache: dict[tuple[str, str], dict[str, bool]] = {}


def _principal_key(p: Principal) -> str:
    return f"{p.user_id}|{p.company_id}|{','.join(sorted(p.group_ids))}|{int(p.is_authenticated)}"


def invalidate(resource_type: str, resource_id: str) -> None:
    """Drop cached decisions for a resource (call on grant/scope change)."""
    _cache.pop((resource_type, resource_id), None)


async def can_access(
    session: AsyncSession,
    principal: Principal,
    resource_type: str,
    resource_id: str,
    resource: ResourceDescriptor,
) -> bool:
    """Return True if principal may access the resource (scope OR explicit grant)."""
    bucket = _cache.setdefault((resource_type, resource_id), {})
    pkey = _principal_key(principal)
    if pkey in bucket:
        return bucket[pkey]
    has = await store.has_grant(session, resource_type, resource_id, principal)
    decision = is_visible(principal, resource, has)
    bucket[pkey] = decision
    return decision


async def repair_grant(
    session: AsyncSession,
    resource_type: str,
    resource_id: str,
    grantee_type: str,
    grantee_id: str,
    *,
    permission: str,
    actor_user_id: str,
) -> ResourceGrant:
    """Admin break-glass repair for an unreachable resource (#15779).

    Grants access directly via the generic ``resource_grants`` table rather
    than mutating the concrete resource's own owner/scope columns: this
    module is resource-type-agnostic and has no write path to those columns
    (they live on whichever table `resource_type` names), while a grant is
    the one repair every resource type already honors unconditionally --
    `is_visible()`'s `granted` check short-circuits before any scope rule
    runs. `store.grant()` invalidates the cache itself (#15779), so a
    subsequent `can_access()` call sees the repair with no restart.

    Callers MUST have already authorized `actor_user_id` as an admin before
    calling this -- same trust boundary as every other backend service
    function reached only through an admin-gated route. This function does
    not re-check it, and grants unconditionally.
    """
    row = await store.grant(session, resource_type, resource_id, grantee_type, grantee_id, permission)
    await audit_log(
        operation="resource.repair_grant",
        result="success",
        user_id=actor_user_id,
        resource=f"{resource_type}:{resource_id}",
        details={
            "grantee_type": grantee_type,
            "grantee_id": grantee_id,
            "permission": permission,
        },
    )
    return row
