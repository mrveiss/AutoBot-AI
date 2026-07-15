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
