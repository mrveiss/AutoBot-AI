# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure visibility rule for scoped resources (#11277)."""

from dataclasses import dataclass

from autobot_shared.scoping.scope_level import ScopeLevel


@dataclass(frozen=True)
class Principal:
    """Who is asking."""

    user_id: str
    company_id: str | None
    group_ids: frozenset[str]


@dataclass(frozen=True)
class ResourceDescriptor:
    """The resource's ownership + scope."""

    owner_id: str
    company_id: str | None
    scope: ScopeLevel
    group_id: str | None = None


def is_visible(principal: Principal, resource: ResourceDescriptor, has_grant: bool) -> bool:
    """Decide whether `principal` may access `resource`.

    `has_grant` is the pre-computed result of "a matching resource_grants row
    exists for this principal" (Task 6). An explicit grant always grants access.
    """
    if principal.user_id == resource.owner_id:
        return True
    if has_grant:
        return True
    if resource.scope is ScopeLevel.ORGANIZATION:
        return resource.company_id is not None and resource.company_id == principal.company_id
    if resource.scope is ScopeLevel.GROUP:
        return resource.group_id is not None and resource.group_id in principal.group_ids
    # USER / SESSION / SHARED are private absent ownership or an explicit grant.
    return False
